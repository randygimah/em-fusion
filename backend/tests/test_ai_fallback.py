"""The correctness fallback: model arm to template. Spec: ai-007.

A model answers and the answer cannot be used -- it cites a rule the bundle
does not carry, or it does not fit the shape at all. The analyst must see
neither that hypothesis nor an error, so the request is retried a **fixed**
number of times and then the mechanical explanation is produced instead,
with a record of why.

Four things carry this suite.

**The ceiling, and the record, are one deliverable.** The ceiling exists
because a retry loop is the realistic route to an unexpected bill -- not
the campaign, which is pennies. The record exists because a mechanical
explanation that arrived *because the model failed* and one that arrived
because the template was what we asked for look identical on screen, and
must not look identical in the data.

**This is not the availability fallback, and the likeliest error in the
item is merging them.** Both end with the analyst reading something other
than the primary arm's output. But an unreachable provider means nothing
was wrong with the question, and a bad answer means the question reached a
model. `ai-003` made the distinction expressible; this suite proves it is
*observed*: a `ProviderUnavailable` raised here must pass straight through
untouched, unretried and unfallen-back-from.

**The two refusal categories are told apart by origin.** A refusal raised
by the generator is malformed -- for a schema-constrained arm that means
the provider broke its own guarantee, which is a more alarming event than
an ungrounded claim and is recorded as its own category rather than folded
into a retry count. A refusal raised by the injected grounding check is
ungrounded. Neither `ai-004` nor `ai-008` has to agree on a shared flag.

**The two categories leave records of different strength.** An ungrounded
hypothesis parsed, so it is a storable row carrying grounding FAILED beside
the template row that replaced it. A malformed response never became a
hypothesis, so it leaves no row at all -- only a log line and a counted
call. The asymmetry is asserted here rather than discovered later.

The grounding check is **injected**, because `ai-008` is built after this.
`None` means no check and has to be written, because forgetting a check and
deciding against one must not look alike.

**Eleven of these pass against a do-nothing stub, and are named rather
than pretended away**: seven assert properties of the *declaration* -- the
two no-default signature checks, the frozen check, the port check, the
agreement between the port's method and the recording one, and the two
import checks -- and four assert a negative, since an implementation that
catches nothing has "does not catch `ProviderUnavailable`" for free. Those
four were sharpened anyway, by scripting a second answer the arm would give
if it were wrongly retried, so the realistic defect -- catching
`GenerationError`, the parent of both categories -- returns a hypothesis
where the test demands a raise. Two others passed against the stub for a
reason other than their name and were rewritten: one could not tell
"checked and passed" from "never checked", and one asserted that `None`
means no check on an implementation that ran no check under any setting.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import logging
from pathlib import Path

import pytest

from app.ai.fallback import (
    CorrectnessFallback,
    FallbackOutcome,
    RefusalCategory,
    Refusal,
)
from app.ai.providers.template import TemplateGenerator
from app.ai.service import (
    ConfigurationError,
    GenerationError,
    GenerationRefused,
    GenerationResult,
    GeneratorKind,
    HypothesisGenerator,
    ProviderUnavailable,
)
from app.ai.template import TemplateError
from app.detection.bundle import EvidenceBundle
from tests.test_ai_service import a_call, a_hypothesis, template_config
from tests.test_ai_template import fault_bundle

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FALLBACK_SOURCE = BACKEND_ROOT / "app" / "ai" / "fallback.py"


# ------------------------------------------------------------------ the doubles


class _ScriptedArm:
    """A generator doing exactly what the test scripted, in order.

    A `GenerationResult` is returned; an exception instance is raised. It
    counts its calls, because "how many times did we pay" is the assertion
    the ceiling exists for and it cannot be made any other way.
    """

    def __init__(self, *script: GenerationResult | BaseException) -> None:
        self.script = list(script)
        self.calls = 0

    def generate(self, bundle: EvidenceBundle) -> GenerationResult:
        self.calls += 1
        if not self.script:
            raise AssertionError(
                f"the arm was called {self.calls} times; the test scripted fewer"
            )
        action = self.script.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


class _ScriptedCheck:
    """A grounding check standing in for `ai-008`. `None` passes."""

    def __init__(self, *script: BaseException | None) -> None:
        self.script = list(script)
        self.calls = 0

    def __call__(self, hypothesis, bundle: EvidenceBundle) -> None:
        self.calls += 1
        if not self.script:
            raise AssertionError("the check was called more times than scripted")
        outcome = self.script.pop(0)
        if outcome is not None:
            raise outcome


def model_result(**kw) -> GenerationResult:
    kw.setdefault("hypothesis", a_hypothesis())
    kw.setdefault("generator", GeneratorKind.HOSTED)
    kw.setdefault("call", a_call())
    return GenerationResult(**kw)


def a_template_arm() -> TemplateGenerator:
    """The real fallback, not a double -- the composition is the claim."""
    return TemplateGenerator(template_config())


def a_fallback(primary, fallback=None, *, check=None, max_attempts=2):
    return CorrectnessFallback(
        primary,
        a_template_arm() if fallback is None else fallback,
        check=check,
        max_attempts=max_attempts,
    )


# ------------------------------------------------- the ceiling is stated, never assumed


def test_a_ceiling_below_one_attempt_is_refused():
    # spec: ai-007 -- zero attempts is a generator that never runs, reported
    # as a correctness fallback. It is a configuration error, not a policy.
    with pytest.raises(ConfigurationError) as raised:
        a_fallback(_ScriptedArm(), max_attempts=0)

    assert "0" in str(raised.value)


def test_a_negative_ceiling_is_refused():
    # spec: ai-007
    with pytest.raises(ConfigurationError):
        a_fallback(_ScriptedArm(), max_attempts=-1)


def test_a_ceiling_of_one_attempt_is_legitimate_and_means_no_retry():
    # spec: ai-007 -- "do not retry" is a real answer, and the one the
    # determinism probe may well return. It must be expressible, not a
    # degenerate case that trips the guard.
    arm = _ScriptedArm(GenerationRefused("cannot be parsed"))

    outcome = a_fallback(arm, max_attempts=1).generate_recorded(fault_bundle())

    assert arm.calls == 1
    assert outcome.fell_back is True


def test_the_ceiling_has_no_default():
    # spec: ai-007 -- a retry count is a spending decision, and one made by
    # omission is one nobody chose. Same rule as GenerationConfig.model_id.
    parameter = inspect.signature(CorrectnessFallback.__init__).parameters
    assert parameter["max_attempts"].default is inspect.Parameter.empty


def test_the_grounding_check_has_no_default():
    # spec: ai-007, ai-008 -- None means "no check" and must be written.
    # Forgetting a check and deciding against one must not look alike, which
    # is evb-001's typed absence at the one place it would be cheapest to
    # skip: ai-008 does not exist yet, so a default would be None forever.
    parameter = inspect.signature(CorrectnessFallback.__init__).parameters
    assert parameter["check"].default is inspect.Parameter.empty


def test_the_fallback_cannot_be_the_primary():
    # spec: ai-007 -- a fallback that is the thing it is falling back from
    # fails identically and reports the failure as a recovery.
    arm = _ScriptedArm()

    with pytest.raises(ConfigurationError) as raised:
        CorrectnessFallback(arm, arm, check=None, max_attempts=2)

    assert "fallback" in str(raised.value).lower()


# ------------------------------------------------------------ the ordinary path


def test_a_usable_first_answer_is_returned_untouched():
    # spec: ai-007 -- the overwhelmingly common case costs one call and
    # leaves no refusals behind.
    result = model_result()
    arm = _ScriptedArm(result)
    check = _ScriptedCheck(None)

    outcome = a_fallback(arm, check=check).generate_recorded(fault_bundle())

    assert outcome.result is result
    assert outcome.refusals == ()
    assert outcome.fell_back is False
    assert arm.calls == 1
    # Without this the test cannot tell "checked and passed" from "never
    # checked", and both satisfy every other line above.
    assert check.calls == 1


def test_a_none_check_runs_no_check_at_all():
    # spec: ai-007, ai-008 -- before ai-008 exists, and for an arm whose
    # output is grounded by construction, the honest configuration is no
    # check rather than a check that always passes.
    result = model_result()
    refusing = _ScriptedCheck(*[GenerationRefused("ungrounded") for _ in range(2)])

    unchecked = a_fallback(_ScriptedArm(result), check=None).generate_recorded(
        fault_bundle()
    )
    # The same arm, the same answer, and a check that refuses it: the only
    # difference is the check, so the pair proves None is honoured rather
    # than proving checks are never run at all.
    checked = a_fallback(
        _ScriptedArm(result, model_result()), check=refusing
    ).generate_recorded(fault_bundle())

    assert unchecked.result is result
    assert unchecked.fell_back is False
    assert checked.fell_back is True


def test_it_satisfies_the_generation_port():
    # spec: ai-007, ai-003 -- a decorator over the port, so ai-004 and
    # ai-005 never learn that retry exists. Anything holding a generator can
    # hold this one.
    wrapped = a_fallback(_ScriptedArm(model_result()), check=None)

    assert isinstance(wrapped, HypothesisGenerator)


def test_generate_returns_the_recorded_outcomes_own_result():
    # spec: ai-007 -- the port's method and the recording one must not be
    # two behaviours. One is the other with the trail dropped.
    result = model_result()

    returned = a_fallback(_ScriptedArm(result), check=None).generate(fault_bundle())

    assert returned is result


# ------------------------------------------------ retrying, and stopping


def test_a_malformed_answer_is_retried_and_a_good_second_answer_is_kept():
    # spec: ai-007 -- a retry that works leaves a refusal in the record and
    # does NOT report a fallback. The record and the outcome are different
    # facts.
    good = model_result()
    arm = _ScriptedArm(GenerationRefused("not valid against the schema"), good)

    outcome = a_fallback(arm, check=_ScriptedCheck(None)).generate_recorded(
        fault_bundle()
    )

    assert outcome.result is good
    assert outcome.fell_back is False
    assert [refusal.category for refusal in outcome.refusals] == [
        RefusalCategory.MALFORMED
    ]


def test_an_ungrounded_answer_is_retried_and_a_grounded_second_answer_is_kept():
    # spec: ai-007, ai-008
    good = model_result()
    arm = _ScriptedArm(model_result(), good)
    check = _ScriptedCheck(GenerationRefused("cites RF-NOISE-999"), None)

    outcome = a_fallback(arm, check=check).generate_recorded(fault_bundle())

    assert outcome.result is good
    assert outcome.fell_back is False
    assert [refusal.category for refusal in outcome.refusals] == [
        RefusalCategory.UNGROUNDED
    ]


def test_the_ceiling_is_the_exact_number_of_calls_made():
    # spec: ai-007 -- the failure case. A loop bug is the realistic route to
    # an unexpected bill, so "bounded" is asserted as a count and not as the
    # absence of a hang.
    arm = _ScriptedArm(*[GenerationRefused("no") for _ in range(3)])

    a_fallback(arm, max_attempts=3).generate_recorded(fault_bundle())

    assert arm.calls == 3


def test_reaching_the_ceiling_produces_the_template_and_says_so():
    # spec: ai-007, ai-002 -- the analyst gets an explanation, not an error,
    # and the row records which generator wrote it.
    arm = _ScriptedArm(GenerationRefused("no"), GenerationRefused("still no"))

    outcome = a_fallback(arm).generate_recorded(fault_bundle())

    assert outcome.fell_back is True
    assert outcome.result.generator is GeneratorKind.TEMPLATE
    assert outcome.result.call is None
    assert len(outcome.refusals) == 2


def test_succeeding_on_the_last_allowed_attempt_is_not_a_fallback():
    # spec: ai-007 -- the boundary. One refusal short of the ceiling is a
    # model hypothesis, and reporting it as a fallback would understate the
    # model arm in a pre-registered comparison.
    good = model_result()
    arm = _ScriptedArm(GenerationRefused("no"), good)

    outcome = a_fallback(arm, max_attempts=2).generate_recorded(fault_bundle())

    assert outcome.result is good
    assert outcome.fell_back is False
    assert len(outcome.refusals) == 1


def test_the_template_is_asked_once_and_only_after_the_ceiling():
    # spec: ai-007 -- the fallback is not a parallel arm. It runs when the
    # model arm is out of attempts and never otherwise.
    fallback_arm = _ScriptedArm(
        GenerationResult(
            hypothesis=a_hypothesis(), generator=GeneratorKind.TEMPLATE, call=None
        )
    )
    arm = _ScriptedArm(GenerationRefused("no"), GenerationRefused("no"))

    a_fallback(arm, fallback_arm).generate_recorded(fault_bundle())

    assert fallback_arm.calls == 1


def test_the_two_categories_are_recorded_in_the_order_they_happened():
    # spec: ai-007 -- one arm can fail both ways across a retry, and the
    # trail is a sequence rather than a tally.
    arm = _ScriptedArm(GenerationRefused("malformed"), model_result())
    check = _ScriptedCheck(GenerationRefused("ungrounded"))

    outcome = a_fallback(arm, check=check).generate_recorded(fault_bundle())

    assert [refusal.category for refusal in outcome.refusals] == [
        RefusalCategory.MALFORMED,
        RefusalCategory.UNGROUNDED,
    ]
    assert [refusal.attempt for refusal in outcome.refusals] == [1, 2]


# --------------------------------------------- told apart by origin, not by a flag


def test_a_refusal_from_the_generator_is_malformed_and_leaves_no_hypothesis():
    # spec: ai-007 -- §10's amendment. For a schema-constrained arm this is
    # the provider breaking its own guarantee, and it is the failure with
    # the weakest record: nothing parsed, so there is no row to store.
    arm = _ScriptedArm(GenerationRefused("truncated JSON"))

    outcome = a_fallback(arm, max_attempts=1).generate_recorded(fault_bundle())

    refusal = outcome.refusals[0]
    assert refusal.category is RefusalCategory.MALFORMED
    assert refusal.result is None


def test_a_refusal_from_the_check_is_ungrounded_and_keeps_what_it_refused():
    # spec: ai-007, ai-008, db-002 -- it parsed, so it is a storable row
    # carrying grounding FAILED beside the template that replaced it. That
    # is why db-002 appends rather than replaces.
    refused = model_result()
    check = _ScriptedCheck(GenerationRefused("cites a rule the bundle lacks"))

    outcome = a_fallback(
        _ScriptedArm(refused), check=check, max_attempts=1
    ).generate_recorded(fault_bundle())

    refusal = outcome.refusals[0]
    assert refusal.category is RefusalCategory.UNGROUNDED
    assert refusal.result is refused


def test_the_reason_is_the_refusals_own_words():
    # spec: ai-007 -- "the fallback reason logged". A reason paraphrased by
    # the layer that caught it is a reason nobody can act on.
    arm = _ScriptedArm(GenerationRefused("cited RF-NOISE-999, absent from bundle"))

    outcome = a_fallback(arm, max_attempts=1).generate_recorded(fault_bundle())

    assert outcome.refusals[0].reason == "cited RF-NOISE-999, absent from bundle"


# -------------------------------------------------- every call is countable (ai-009)


def test_a_refused_generation_still_carries_what_it_paid_for():
    # spec: ai-007, ai-009 -- the realistic route to an unexpected bill is a
    # retry loop, which is only visible if the calls that FAILED are counted
    # too. A malformed response has no result to carry its call, so the
    # refusal carries it.
    call = a_call()
    arm = _ScriptedArm(GenerationRefused("bad shape", call=call))

    outcome = a_fallback(arm, max_attempts=1).generate_recorded(fault_bundle())

    assert outcome.refusals[0].call is call


def test_an_ungrounded_refusals_call_is_read_from_the_result_it_kept():
    # spec: ai-007, ai-009 -- one place to read the call from, whichever way
    # the attempt failed. A value stored twice eventually disagrees with
    # itself while both halves keep working.
    refused = model_result()
    check = _ScriptedCheck(GenerationRefused("ungrounded"))

    outcome = a_fallback(
        _ScriptedArm(refused), check=check, max_attempts=1
    ).generate_recorded(fault_bundle())

    assert outcome.refusals[0].call is refused.call


def test_a_refusal_the_arm_recorded_nothing_for_carries_no_call():
    # spec: ai-007, ai-009 -- an arm that failed before the provider
    # answered spent nothing, and inventing a zero-token call here would
    # make an unpaid attempt indistinguishable from a free one.
    arm = _ScriptedArm(GenerationRefused("could not build the request"))

    outcome = a_fallback(arm, max_attempts=1).generate_recorded(fault_bundle())

    assert outcome.refusals[0].call is None


def test_every_attempt_of_an_exhausted_run_is_in_the_trail():
    # spec: ai-007, ai-009 -- the budget counts attempts, so all of them
    # must survive to the caller. Three calls, three records.
    arm = _ScriptedArm(*[GenerationRefused("no", call=a_call()) for _ in range(3)])

    outcome = a_fallback(arm, max_attempts=3).generate_recorded(fault_bundle())

    assert len(outcome.refusals) == 3
    assert sum(r.call.usage.prompt_tokens for r in outcome.refusals if r.call) == 300


# --------------------------- what must NOT be caught: the other fallback, and errors


def test_an_unreachable_provider_is_not_caught_here():
    # spec: ai-007, ai-006 -- THE failure case of this item. Both fallbacks
    # end with the analyst reading something else, which is what makes
    # merging them easy; but nothing was wrong with the request, so the
    # answer is to ask somewhere else, not to give up on the question.
    # The second entry is what makes this discriminating: an implementation
    # catching GenerationError -- the parent of both categories -- would
    # retry, succeed, and return a hypothesis instead of raising.
    arm = _ScriptedArm(ProviderUnavailable("connection refused"), model_result())

    with pytest.raises(ProviderUnavailable):
        a_fallback(arm).generate_recorded(fault_bundle())

    assert arm.calls == 1


def test_an_unreachable_provider_consumes_no_retries_and_no_template():
    # spec: ai-007, ai-006 -- not caught means not retried either. A retry
    # against an unreachable provider is the "retrying the same place
    # harder" error the phase document names.
    fallback_arm = _ScriptedArm()
    arm = _ScriptedArm(ProviderUnavailable("timed out"), model_result())

    with pytest.raises(ProviderUnavailable):
        a_fallback(arm, fallback_arm, max_attempts=3).generate_recorded(fault_bundle())

    assert arm.calls == 1
    assert fallback_arm.calls == 0


def test_a_misconfiguration_is_not_caught_here():
    # spec: ai-007, ai-003 -- ConfigurationError is not a GenerationError on
    # purpose. Caught here it would produce mechanical output for every
    # bundle while the run reported itself as hosted.
    arm = _ScriptedArm(ConfigurationError("no model id"), model_result())

    with pytest.raises(ConfigurationError):
        a_fallback(arm).generate_recorded(fault_bundle())

    assert arm.calls == 1


def test_an_unrelated_exception_passes_straight_through():
    # spec: ai-007 -- the fallback responds to refusals, not to bugs.
    # Swallowing a TypeError here would turn a defect into a quietly
    # degraded arm.
    arm = _ScriptedArm(RuntimeError("a defect, not a refusal"), model_result())

    with pytest.raises(RuntimeError):
        a_fallback(arm).generate_recorded(fault_bundle())

    assert arm.calls == 1


def test_a_template_that_refuses_carries_the_models_refusal_as_its_cause():
    # spec: ai-007, ai-002 -- the template is what both fallbacks fall back
    # TO, so its own refusal has nowhere to go and must surface. It must
    # surface WITH the model refusal that summoned it, or the investigation
    # starts from a bundle nothing could explain and never learns a model
    # was asked twice first.
    fallback_arm = _ScriptedArm(TemplateError("no single verdict item"))
    arm = _ScriptedArm(GenerationRefused("the model's last word"))

    with pytest.raises(TemplateError) as raised:
        a_fallback(arm, fallback_arm, max_attempts=1).generate_recorded(fault_bundle())

    assert isinstance(raised.value.__cause__, GenerationRefused)
    assert "the model's last word" in str(raised.value.__cause__)


def test_a_template_failure_is_not_itself_retried():
    # spec: ai-007 -- the ceiling bounds the model arm. Retrying the last
    # resort is the unbounded recursion the item forbids, by another route.
    fallback_arm = _ScriptedArm(TemplateError("nothing to explain"))
    arm = _ScriptedArm(*[GenerationRefused("no") for _ in range(2)])

    with pytest.raises(GenerationError):
        a_fallback(arm, fallback_arm, max_attempts=2).generate_recorded(fault_bundle())

    assert fallback_arm.calls == 1


# ----------------------------------------------------- the records refuse to lie


def test_an_attempt_number_below_one_is_refused():
    # spec: ai-007 -- attempts are 1-based because "attempt 0" is not an
    # event that happened.
    with pytest.raises(GenerationError):
        Refusal(
            attempt=0,
            category=RefusalCategory.MALFORMED,
            reason="no",
            result=None,
            refused_call=None,
        )


def test_a_reason_of_whitespace_is_refused():
    # spec: ai-007 -- an empty reason satisfies a check for "populated"
    # while recording nothing, which is worse than absent. Same rule as
    # ai-003's ModelCall.
    with pytest.raises(GenerationError):
        Refusal(
            attempt=1,
            category=RefusalCategory.MALFORMED,
            reason="   ",
            result=None,
            refused_call=None,
        )


def test_an_ungrounded_refusal_without_the_hypothesis_it_refused_is_impossible():
    # spec: ai-007, db-002 -- ungrounded means it parsed. A record saying
    # otherwise would lose the one row db-002 appends for exactly this case.
    with pytest.raises(GenerationError):
        Refusal(
            attempt=1,
            category=RefusalCategory.UNGROUNDED,
            reason="cites a rule the bundle lacks",
            result=None,
            refused_call=None,
        )


def test_a_malformed_refusal_carrying_a_result_is_impossible():
    # spec: ai-007 -- the other direction. Malformed means nothing parsed.
    with pytest.raises(GenerationError):
        Refusal(
            attempt=1,
            category=RefusalCategory.MALFORMED,
            reason="truncated",
            result=model_result(),
            refused_call=None,
        )


def test_an_ungrounded_refusal_cannot_carry_a_second_copy_of_its_call():
    # spec: ai-007 -- its call lives inside the result it kept. A second
    # place to put it is a second place for it to disagree.
    with pytest.raises(GenerationError):
        Refusal(
            attempt=1,
            category=RefusalCategory.UNGROUNDED,
            reason="ungrounded",
            result=model_result(),
            refused_call=a_call(),
        )


def test_a_fallback_with_nothing_to_fall_back_from_is_impossible():
    # spec: ai-007 -- fell_back is the fact the analyst's row depends on,
    # and it cannot be true with no refusal behind it.
    with pytest.raises(GenerationError):
        FallbackOutcome(result=model_result(), refusals=(), fell_back=True)


def test_the_records_are_frozen():
    # spec: ai-007, NFR-602 -- the trail is evidence about a campaign, and
    # evidence that can be edited after the fact is not evidence.
    outcome = a_fallback(
        _ScriptedArm(model_result()), check=None
    ).generate_recorded(fault_bundle())

    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.fell_back = True


def test_the_trail_is_a_tuple_rather_than_the_list_it_was_built_from():
    # spec: ai-007 -- a caller appending to the record of what happened
    # would be writing history, and a list invites exactly that.
    arm = _ScriptedArm(GenerationRefused("no"))

    outcome = a_fallback(arm, max_attempts=1).generate_recorded(fault_bundle())

    assert isinstance(outcome.refusals, tuple)


# ---------------------------------------------------------------- it is logged


def test_each_refusal_is_logged_with_its_category(caplog):
    # spec: ai-007 -- "the fallback reason logged". The malformed category
    # is the one this matters most for: it leaves no row, so the log line is
    # its only record.
    arm = _ScriptedArm(GenerationRefused("truncated JSON"))

    with caplog.at_level(logging.WARNING, logger="app.ai.fallback"):
        a_fallback(arm, max_attempts=1).generate_recorded(fault_bundle())

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "malformed" in logged
    assert "truncated JSON" in logged


def test_falling_back_to_the_template_is_logged(caplog):
    # spec: ai-007 -- the named failure case is falling back WITHOUT
    # recording that a fallback occurred.
    arm = _ScriptedArm(*[GenerationRefused("no") for _ in range(2)])

    with caplog.at_level(logging.WARNING, logger="app.ai.fallback"):
        a_fallback(arm, max_attempts=2).generate_recorded(fault_bundle())

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "template" in logged.lower()


# ------------------------------------------------- the template is not wired in


def test_this_module_does_not_reach_for_the_template_itself():
    # spec: ai-007, ai-003 -- the fallback is injected, like registry's
    # provider mapping and api-006's batch launcher. Importing ai-002 here
    # would make this a special case carved beside the port rather than the
    # port's own pattern, and the suite could then never drive it with
    # anything else.
    tree = ast.parse(FALLBACK_SOURCE.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    assert not [
        name
        for name in imported
        if name.startswith("app.ai.providers") or name == "app.ai.template"
    ], imported


def test_the_import_check_would_notice_a_module_that_did():
    # spec: ai-007 -- the walker above passes trivially on a module with no
    # imports at all, so it is fired once at a module that genuinely does
    # import the template.
    source = BACKEND_ROOT / "app" / "ai" / "providers" / "template.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    ]

    assert "app.ai.template" in imported
