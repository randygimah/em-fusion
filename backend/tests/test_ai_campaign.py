"""The campaign run over a fixed bundle sample. Spec: ai-012.

Everything needed to ask one question exists, is tested and is measured.
This is the job that asks twenty of them and comes out with a record honest
enough to publish a number from -- and it is a capability rather than a
loop, because three of the things it has to get right have no symptom when
it gets them wrong.

**The record the port would have dropped.** `ai-003`'s `generate` returns
the delivered hypothesis and nothing else. An ungrounded attempt *parsed*,
so it is a storable row that `db-002` appends with grounding FAILED beside
the one that replaced it -- and through the port that row simply does not
exist. Every bundle still gets an explanation and the catch rate still
reports a number, with no rows behind it.

**The grounding count, once per generation.** `ai-007`'s injected checker
already feeds the ledger on every attempt it examines, so a campaign that
re-checked the delivered hypothesis through the same checker would count
the model arm twice and halve its catch rate. The verdict that goes in the
row therefore comes from the pure check, and the ledger is fed from exactly
one place per arm.

**What aborts and what is skipped.** A per-bundle generation failure is
recorded and skipped, because a campaign that dies on bundle 14 of 20 has
spent the money and kept nothing. `BudgetExceeded` and `ConfigurationError`
stop the run -- they sit outside the `GenerationError` tree precisely so
that no enclosing handler can convert them into template output while every
row reports itself as hosted. Stopping still keeps the account of what was
already stored, for the same reason skipping exists.

These tests need a database, because storing is half of what the item does.
They make no network call: the arm is injected through `ai-011`'s registry.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.ai.assembly import assemble_arm
from app.ai.budget import BudgetExceeded, CallBudget
from app.ai.campaign import (
    CampaignAborted,
    CampaignRecord,
    GenerationRecord,
    run_campaign,
)
from app.ai.grounding import GroundingLedger
from app.ai.providers.template import TemplateGenerator
from app.ai.service import (
    ConfigurationError,
    GenerationRefused,
    GenerationResult,
    GeneratorKind,
    ProviderUnavailable,
    Usage,
)
from app.ai.template import TemplateError
from app.ai.template import generate as template_generate
from app.db.bundles import save_bundles, stored_bundles_for_run
from app.db.hypotheses import (
    GroundingStatus,
    HypothesisWriteError,
    hypotheses_for_bundle,
)
from tests.conftest import RUN_ID, START, requires_database
from tests.test_ai_assembly import _RecordingFactory, registry, ungrounded
from tests.test_ai_fallback import model_result
from tests.test_ai_service import a_call, template_config
from tests.test_ai_template import fault_bundle, zone_bundle
from tests.test_evb_traceability import insert_rf

MODEL = "some-model-2026-01-01"


# ------------------------------------------------------------------ the corpus


@pytest.fixture
def sample(migrated_database: Engine, factory: sessionmaker) -> list:
    """Two stored bundles of the two kinds, in the shape `evb-002` returns.

    One interference and one fault, because the two differ in size by about
    3.2x and in whether they carry a track side at all -- a sample of one
    kind would exercise half of what a campaign meets.
    """
    from dataclasses import replace

    for sensor in ("RF-03", "RF-04"):
        insert_rf(migrated_database, run_id=RUN_ID, sensor=sensor, channel=4, at=START)
    save_bundles(
        factory,
        scenario_run_id=RUN_ID,
        bundles=[
            replace(zone_bundle(tracks=False), scenario_run_id=RUN_ID),
            replace(fault_bundle(), scenario_run_id=RUN_ID),
        ],
    )
    return stored_bundles_for_run(factory, RUN_ID)


# ------------------------------------------------------------------ the doubles


class _HonestArm:
    """A model arm that answers **the bundle it was asked about**, correctly.

    Anything in `script` happens first, in order -- a result is returned and
    an exception is raised -- and once it runs out every further call is an
    ordinary grounded answer.

    Deriving the answer from the bundle is not a convenience. The first
    version of these doubles returned a fixed hypothesis grounded in one
    bundle and the sample holds two, so the model arm was ungrounded on
    half of them and three tests failed for reasons that had nothing to do
    with what they were testing. A model that answers correctly must answer
    correctly about *this* bundle.
    """

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.calls = 0

    def generate(self, bundle):
        self.calls += 1
        if self.script:
            action = self.script.pop(0)
            if isinstance(action, BaseException):
                raise action
            return action
        return model_result(
            hypothesis=template_generate(bundle),
            # Distinct per call, so a test asserting on stored rows is not
            # asserting on rows that were identical anyway.
            call=a_call(raw_response=json.dumps({"call": self.calls})),
        )


def arm(*script, budget=None, ledger=None, max_attempts=2):
    """An assembled hosted arm over `_HonestArm`, scripted where a test needs it."""
    return assemble_arm(
        arm=GeneratorKind.HOSTED,
        provider="stub",
        model_id=MODEL,
        parameters={"temperature": 0.0, "seed": 7},
        budget=budget or CallBudget(max_calls=50, max_cost_usd=None),
        ledger=ledger or GroundingLedger(),
        max_attempts=max_attempts,
        providers=registry(_RecordingFactory(_HonestArm(*script))),
    )


def baseline() -> TemplateGenerator:
    """The real template behind the port, not a double."""
    return TemplateGenerator(template_config())


def campaign(sample, *, generations=1, **kw) -> CampaignRecord:
    kw.setdefault("arm", arm())
    kw.setdefault("baseline", baseline())
    return run_campaign(kw.pop("factory"), sample=sample, generations=generations, **kw)


def for_arm(record: CampaignRecord, kind: GeneratorKind) -> list[GenerationRecord]:
    return [g for g in record.generations if g.requested_arm is kind]


# --------------------------------------------------------------- what it runs


@pytest.mark.database
@requires_database
def test_every_bundle_in_the_sample_is_asked_of_both_arms(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, eval-004 -- the scored pack is paired within bundle, so
    # both arms see the same evidence or the pairing means nothing.
    record = campaign(sample, factory=factory)

    assert {g.bundle_id for g in for_arm(record, GeneratorKind.HOSTED)} == {
        bundle_id for bundle_id, _ in sample
    }
    assert {g.bundle_id for g in for_arm(record, GeneratorKind.TEMPLATE)} == {
        bundle_id for bundle_id, _ in sample
    }


@pytest.mark.database
@requires_database
def test_the_model_arm_is_asked_the_configured_number_of_times(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, eval-004 -- three generations per bundle, of which
    # eval-004 scores the first. The premise that one was enough -- that
    # temperature 0 returns the identical answer -- was measured false.
    record = campaign(sample, factory=factory, generations=3)

    assert len(for_arm(record, GeneratorKind.HOSTED)) == 3 * len(sample)


@pytest.mark.database
@requires_database
def test_the_baseline_is_asked_once_however_many_the_model_is_asked(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, eval-004 -- the template has no provider in it, so its
    # single generation is safe for exactly the reason the model arm's was
    # not. Asking three times would prove nothing and would put two more
    # identical rows in the way of every count.
    record = campaign(sample, factory=factory, generations=3)

    assert len(for_arm(record, GeneratorKind.TEMPLATE)) == len(sample)


@pytest.mark.database
@requires_database
def test_each_generation_is_numbered_within_its_bundle_and_arm(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, eval-004 -- eval-004 scores generation 1, so it has to
    # be identifiable as generation 1 rather than found by row order, which
    # is the heap-order failure this repository has recorded three times.
    record = campaign(sample, factory=factory, generations=3)

    for bundle_id, _ in sample:
        hosted = [
            g.ordinal
            for g in for_arm(record, GeneratorKind.HOSTED)
            if g.bundle_id == bundle_id
        ]
        assert hosted == [1, 2, 3]


@pytest.mark.database
@requires_database
def test_every_generation_is_stored_and_the_record_says_where(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, db-002 -- the record is an account of rows, not of
    # objects in memory, or nothing downstream can find what was generated.
    record = campaign(sample, factory=factory, generations=2)

    for bundle_id, _ in sample:
        stored = {row.id for row in hypotheses_for_bundle(factory, bundle_id)}
        named = {
            g.hypothesis_id for g in record.generations if g.bundle_id == bundle_id
        } | {
            refusal.hypothesis_id
            for g in record.generations
            if g.bundle_id == bundle_id
            for refusal in g.refusals
            if refusal.hypothesis_id is not None
        }
        assert named == stored, "every row is accounted for, refusals included"


@pytest.mark.database
@requires_database
def test_the_stored_rows_say_which_arm_was_asked(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, db-002 -- the campaign is the caller that column was
    # added for, so it has to be the caller that fills it correctly.
    record = campaign(sample, factory=factory)
    bundle_id = sample[0][0]

    rows = hypotheses_for_bundle(factory, bundle_id)

    assert [row.requested_generator for row in rows] == [
        GeneratorKind.HOSTED,
        GeneratorKind.TEMPLATE,
    ], "the model arm runs first, so a template row before one is not a fallback"
    asked = [g.requested_arm for g in record.generations if g.bundle_id == bundle_id]
    assert asked == [GeneratorKind.HOSTED, GeneratorKind.TEMPLATE]


# ---------------------------------------------- the rows the port would drop


@pytest.mark.database
@requires_database
def test_an_ungrounded_attempt_is_stored_with_the_verdict_that_rejected_it(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-007, ai-008, db-002 -- the row db-002 appends and
    # never replaces. Through ai-003's port it does not exist at all, and
    # nothing says it is missing.
    bundle_id, bundle = sample[0]
    invented = ungrounded(bundle)
    record = campaign(
        [sample[0]],
        factory=factory,
        arm=arm(*(model_result(hypothesis=invented) for _ in range(2))),
    )

    generation = for_arm(record, GeneratorKind.HOSTED)[0]
    assert generation.fell_back
    assert [r.hypothesis_id is not None for r in generation.refusals] == [True, True]
    rejected = {
        row.id: row
        for row in hypotheses_for_bundle(factory, bundle_id)
        if row.id in {r.hypothesis_id for r in generation.refusals}
    }
    assert len(rejected) == 2
    for row in rejected.values():
        assert row.grounding is GroundingStatus.FAILED
        assert row.generator is GeneratorKind.HOSTED
        assert row.requested_generator is GeneratorKind.HOSTED


@pytest.mark.database
@requires_database
def test_a_malformed_attempt_leaves_a_record_and_no_row(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-007, db-002 -- nothing parsed, so there is no
    # hypothesis and no row: a reason and a counted call are its entire
    # record. Storing one anyway would invent a hypothesis nobody wrote.
    bundle_id, _ = sample[0]
    record = campaign(
        [sample[0]],
        factory=factory,
        arm=arm(*(GenerationRefused("not JSON at all") for _ in range(2))),
    )

    generation = for_arm(record, GeneratorKind.HOSTED)[0]
    assert generation.fell_back
    assert [r.hypothesis_id for r in generation.refusals] == [None, None]
    assert [r.reason for r in generation.refusals] == ["not JSON at all"] * 2
    assert len(hypotheses_for_bundle(factory, bundle_id)) == 2, (
        "the delivered fallback and the baseline, and nothing for the two "
        "answers that never became hypotheses"
    )


@pytest.mark.database
@requires_database
def test_the_row_a_fallback_delivered_is_not_marked_as_checked(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-007, db-002 -- ai-007 does not check the replacement,
    # deliberately: ai-002 is grounded by construction and a failure there
    # would have nowhere to go. So "not yet checked" is the true value, and
    # writing PASSED would claim a check that never ran.
    bundle_id, bundle = sample[0]
    record = campaign(
        [sample[0]],
        factory=factory,
        arm=arm(*(model_result(hypothesis=ungrounded(bundle)) for _ in range(2))),
    )

    generation = for_arm(record, GeneratorKind.HOSTED)[0]
    checked = for_arm(record, GeneratorKind.TEMPLATE)[0]

    assert generation.grounding is GroundingStatus.NOT_CHECKED
    rows = {row.id: row for row in hypotheses_for_bundle(factory, bundle_id)}
    assert rows[generation.hypothesis_id].grounding is GroundingStatus.NOT_CHECKED
    assert rows[generation.hypothesis_id].fell_back
    # The contrast is the assertion. Without it this passes against anything
    # that never records a verdict at all -- which is the defect this
    # repository has now recorded four times: a test matching something
    # weaker than its name. Found by a permissive stub, before the
    # implementation existed.
    assert rows[checked.hypothesis_id].grounding is GroundingStatus.PASSED
    assert not rows[checked.hypothesis_id].fell_back


@pytest.mark.database
@requires_database
def test_a_model_answer_that_stood_is_stored_with_a_passing_verdict(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-008, db-002 -- the ordinary case, and the one that
    # left every row saying "not yet checked" before db-002 had a writer.
    record = campaign(sample, factory=factory)

    for generation in for_arm(record, GeneratorKind.HOSTED):
        assert generation.grounding is GroundingStatus.PASSED
        assert not generation.fell_back
        # The **row**, not only the record. Asserting the record alone let a
        # mutant delete the write and survive: the campaign would report a
        # verdict it never stored, which is the defect db-002's writer was
        # added for, one layer up. Found by the mutation pass.
        rows = {
            row.id: row for row in hypotheses_for_bundle(factory, generation.bundle_id)
        }
        assert rows[generation.hypothesis_id].grounding is GroundingStatus.PASSED


# ------------------------------------------------- the count, once per arm


@pytest.mark.database
@requires_database
def test_a_flagged_baseline_is_recorded_rather_than_raised(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-008, eval-005 -- ai-002 is grounded by construction,
    # so a flagged baseline is a defect in the **check** and not in the
    # baseline. It is recorded rather than raised for two reasons: eval-005
    # reports the template's catch rate as the oracle reading either way, and
    # raising would let a defect in the instrument destroy a campaign that
    # has already been paid for. Nothing here made the baseline fail until
    # the mutation pass pointed out that swapping `report` for the raising
    # gate changed nothing any test could see.
    class _UngroundedBaseline:
        def generate(self, bundle):
            return GenerationResult(
                hypothesis=ungrounded(bundle),
                generator=GeneratorKind.TEMPLATE,
                call=None,
            )

    bundle_id, _ = sample[0]
    ledger = GroundingLedger()

    record = campaign(
        [sample[0]],
        factory=factory,
        arm=arm(ledger=ledger),
        baseline=_UngroundedBaseline(),
    )

    assert record.skipped == (), "a flagged baseline is not a skipped bundle"
    baseline = for_arm(record, GeneratorKind.TEMPLATE)[0]
    assert baseline.grounding is GroundingStatus.FAILED
    rows = {row.id: row for row in hypotheses_for_bundle(factory, bundle_id)}
    assert rows[baseline.hypothesis_id].grounding is GroundingStatus.FAILED
    assert ledger.catch_rate(GeneratorKind.TEMPLATE) == 1.0


@pytest.mark.database
@requires_database
def test_the_model_arm_is_counted_once_per_generation_and_not_twice(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-008, eval-005 -- ai-007's injected checker already
    # fed the ledger on every attempt it examined. A campaign re-checking
    # the delivered hypothesis through the same checker would count each
    # generation twice and halve the catch rate it reports as a result.
    ledger = GroundingLedger()
    campaign(sample, factory=factory, generations=2, arm=arm(ledger=ledger))

    assert ledger.checked(GeneratorKind.HOSTED) == 2 * len(sample)


@pytest.mark.database
@requires_database
def test_the_baseline_is_checked_into_the_same_ledger(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-008, eval-005 -- ai-002 is grounded by construction,
    # so its catch rate is the oracle: anything flagged there is a defect in
    # the check. One ledger spans the run, as ai-009's budget does.
    ledger = GroundingLedger()
    campaign(sample, factory=factory, arm=arm(ledger=ledger))

    assert ledger.checked(GeneratorKind.TEMPLATE) == len(sample)
    assert ledger.catch_rate(GeneratorKind.TEMPLATE) == 0.0


@pytest.mark.database
@requires_database
def test_the_replacement_is_never_counted_against_the_model_arm(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-008, eval-005 -- a template hypothesis always passes,
    # so counting the stand-in against the hosted arm would dilute the
    # hosted catch rate with template output, in the direction that makes
    # the model arm look better the more often it failed.
    _, bundle = sample[0]
    ledger = GroundingLedger()
    campaign(
        [sample[0]],
        factory=factory,
        arm=arm(
            *(model_result(hypothesis=ungrounded(bundle)) for _ in range(2)),
            ledger=ledger,
        ),
    )

    assert ledger.checked(GeneratorKind.HOSTED) == 2, "the two model attempts"
    assert ledger.caught(GeneratorKind.HOSTED) == 2
    assert ledger.catch_rate(GeneratorKind.HOSTED) == 1.0
    assert ledger.checked(GeneratorKind.TEMPLATE) == 1, "the baseline, not the stand-in"


# ------------------------------------------------- what is skipped, what stops


@pytest.mark.database
@requires_database
def test_a_bundle_the_arm_could_not_answer_is_recorded_and_skipped(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, scn-003, eval-001 -- a campaign that dies on bundle 14
    # of 20 has spent the money and kept nothing. Recorded, not swallowed:
    # a skip nobody counted is a corpus quietly smaller than the one the
    # pre-registration fixed.
    record = campaign(
        sample,
        factory=factory,
        arm=arm(ProviderUnavailable("the provider is down")),
    )

    assert [s.bundle_id for s in record.skipped] == [sample[0][0]]
    assert "provider is down" in record.skipped[0].reason
    assert record.skipped[0].requested_arm is GeneratorKind.HOSTED
    assert [g.bundle_id for g in for_arm(record, GeneratorKind.HOSTED)] == [
        sample[1][0]
    ], "the rest of the sample still ran"


@pytest.mark.database
@requires_database
def test_a_skipped_model_generation_does_not_skip_the_baseline(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, eval-004 -- the pairing is what makes bundle difficulty
    # cancel out of the arm difference, so a bundle with a baseline and no
    # model answer is still worth having and is reported as the pair it is
    # not.
    record = campaign(
        [sample[0]],
        factory=factory,
        arm=arm(ProviderUnavailable("down")),
    )

    assert record.skipped
    assert len(for_arm(record, GeneratorKind.TEMPLATE)) == 1


@pytest.mark.database
@requires_database
def test_a_bundle_the_baseline_refuses_is_recorded_and_skipped(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-002, eval-004 -- the template refuses a bundle whose
    # verdict is missing or ambiguous, because explaining it would force an
    # invention. That bundle then has no baseline, so the pair eval-004
    # scores is incomplete -- and an incomplete pair has to be reported
    # rather than silently half-exported, since the pairing is what makes
    # bundle difficulty cancel out of the arm difference.
    class _RefusingBaseline:
        def generate(self, bundle):
            raise TemplateError("this bundle carries no verdict item")

    record = campaign([sample[0]], factory=factory, baseline=_RefusingBaseline())

    assert [s.requested_arm for s in record.skipped] == [GeneratorKind.TEMPLATE]
    assert "no verdict item" in record.skipped[0].reason
    assert len(for_arm(record, GeneratorKind.HOSTED)) == 1, "the model arm still ran"
    assert for_arm(record, GeneratorKind.TEMPLATE) == []


@pytest.mark.database
@requires_database
def test_a_budget_exhaustion_stops_the_campaign(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-009 -- BudgetExceeded sits outside the GenerationError
    # tree precisely so no enclosing handler turns it into template output
    # while every row reports itself as hosted. A campaign that skipped it
    # per bundle would make the budget inert, one layer up from where
    # ai-009 was worried about.
    with pytest.raises(CampaignAborted) as aborted:
        campaign(
            sample,
            factory=factory,
            generations=3,
            arm=arm(budget=CallBudget(max_calls=2, max_cost_usd=None)),
        )

    assert isinstance(aborted.value.cause, BudgetExceeded)


@pytest.mark.database
@requires_database
def test_stopping_keeps_the_account_of_what_was_already_stored(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-009 -- the same argument that makes a skip recorded
    # rather than swallowed. The calls were paid for and the rows are in the
    # database; an abort that dropped the account of which row was which
    # would leave them unattributable.
    with pytest.raises(CampaignAborted) as aborted:
        campaign(
            sample,
            factory=factory,
            generations=3,
            arm=arm(budget=CallBudget(max_calls=2, max_cost_usd=None)),
        )

    partial = aborted.value.record
    assert len(for_arm(partial, GeneratorKind.HOSTED)) == 2
    assert partial.budget.call_count == 2
    stored = hypotheses_for_bundle(factory, sample[0][0])
    assert {g.hypothesis_id for g in partial.generations} <= {r.id for r in stored}


@pytest.mark.database
@requires_database
def test_a_misconfiguration_stops_the_campaign_rather_than_being_skipped(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-003, ai-004 -- a rejected request means we sent
    # something wrong, and skipping it bundle by bundle would run the whole
    # campaign on template output while every row reported itself as hosted.
    with pytest.raises(CampaignAborted) as aborted:
        campaign(
            sample,
            factory=factory,
            arm=arm(ConfigurationError("the schema was rejected")),
        )

    assert isinstance(aborted.value.cause, ConfigurationError)
    assert len(for_arm(aborted.value.record, GeneratorKind.HOSTED)) == 0


# ---------------------------------------------------- refusals at the boundary


@pytest.mark.database
@requires_database
def test_an_empty_sample_is_refused(factory: sessionmaker) -> None:
    # spec: ai-012, eval-004 -- a campaign over no bundles succeeds, costs
    # nothing and reports a catch rate of None, which reads exactly like a
    # clean run of an arm that was never asked anything.
    with pytest.raises(ConfigurationError, match="no bundles"):
        campaign([], factory=factory)


@pytest.mark.database
@requires_database
def test_a_repeated_bundle_is_refused(factory: sessionmaker, sample: list) -> None:
    # spec: ai-012, eval-004 -- the same bundle twice is counted twice in
    # every per-arm figure while looking like two bundles, and the
    # pre-registered corpus is 20 distinct bundles.
    with pytest.raises(ConfigurationError, match="more than once"):
        campaign([sample[0], sample[0]], factory=factory)


@pytest.mark.database
@requires_database
def test_fewer_than_one_generation_is_refused(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012 -- zero generations asks the model arm nothing and
    # reports every bundle as baseline-only, which is a campaign that did
    # not happen described as one that did.
    with pytest.raises(ConfigurationError, match="generation"):
        campaign(sample, factory=factory, generations=0)


@pytest.mark.database
@requires_database
def test_a_model_arm_supplied_as_the_baseline_is_refused_at_the_write(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, db-002 -- nothing here can tell what a generator will
    # return before it is called, so the guard is db-002's: a row saying the
    # template was asked while a model answered is refused at the boundary.
    # This is that guard being load-bearing rather than decorative.
    with pytest.raises(HypothesisWriteError, match="makes no call"):
        campaign(
            [sample[0]],
            factory=factory,
            baseline=_HonestArm(),
        )


# ------------------------------------------------------------- the artefact


@pytest.mark.database
@requires_database
def test_the_record_serialises_to_json(factory: sessionmaker, sample: list) -> None:
    # spec: ai-012, eval-005 -- the record is an artefact to keep, not a
    # diagnostic, and ai-004 already paid for the alternative: the egress
    # payload was measured against a dict hand-written inside a measurement
    # script, which is a right number about the wrong object.
    record = campaign(sample, factory=factory, generations=2)

    written = json.loads(json.dumps(record.as_json()))

    assert len(written["generations"]) == 3 * len(sample)
    assert written["skipped"] == []
    assert written["budget"]["calls"] == 2 * len(sample)
    assert written["grounding"]["hosted"]["checked"] == 2 * len(sample)
    assert written["grounding"]["template"]["catch_rate"] == 0.0


@pytest.mark.database
@requires_database
def test_an_unpriced_call_makes_the_reported_total_a_lower_bound(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-009, eval-005 -- an unpriced call is unmeasurable
    # rather than free, which is why the budget says whether its total is
    # the total. eval-005 reports actual cost as a *result*, and a figure
    # that quietly omitted the calls it could not price would be worse than
    # no figure. Every other test here prices every call, so a mutant
    # hard-coding the completeness flag survived until this existed.
    bundle_id, bundle = sample[0]
    unpriced = model_result(
        hypothesis=template_generate(bundle),
        call=a_call(
            usage=Usage(prompt_tokens=100, completion_tokens=50, cost_usd=None),
            raw_response='{"priced": false}',
        ),
    )

    record = campaign([sample[0]], factory=factory, arm=arm(unpriced))

    written = json.loads(json.dumps(record.as_json()))
    assert written["budget"]["calls"] == 1
    assert written["budget"]["unpriced_calls"] == 1
    assert written["budget"]["cost_is_complete"] is False
    assert record.generations[0].usage is not None
    assert record.generations[0].usage.cost_usd is None


@pytest.mark.database
@requires_database
def test_an_arm_that_never_ran_reports_null_and_not_zero(
    factory: sessionmaker, sample: list
) -> None:
    # spec: ai-012, ai-008, evb-001 -- zero out of zero is unmeasured. A
    # catch rate of 0.0 for the local arm would read as "the check flagged
    # nothing on it", which is true-looking in exactly the case where that
    # arm was never asked anything.
    record = campaign(sample, factory=factory)

    written = json.loads(json.dumps(record.as_json()))

    assert written["grounding"]["local"]["checked"] == 0
    assert written["grounding"]["local"]["catch_rate"] is None
