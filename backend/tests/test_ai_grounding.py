"""The automated grounding check. Spec: ai-008.

The load-bearing safeguard. Constrained decoding guarantees a hosted
answer's *shape* -- the fields are there, the types are right, confidence
is one of three words -- and says nothing whatever about whether the things
named inside it exist. A perfectly-formed hypothesis citing a rule that was
never run is the failure this whole layer was built around, and this is the
only thing standing in front of it.

It is tractable only because of `evb-001`: the model receives one bundle
and nothing else, so "does this claim refer to something real" is a set
membership test against a closed list rather than an unanswerable question
about 20.7M rows.

**The interesting half is the compartment.** A bundle carries rejected
competing claims in `superseded`, deliberately, so a model can write an
honest alternative instead of pretending none existed. A check that asked
"does this identifier appear anywhere in the bundle" would wave through a
hypothesis citing one of those *as support* -- reading two rules
disagreeing as two rules agreeing, which is the exact error the safeguard
exists to catch. So there are three verdicts and the third never folds into
the second.

**`ai-002` is the oracle and must not share the fault.** A template
hypothesis is grounded by construction, so anything flagged on one is a
defect *here*. That holds only if the two derive the citation key
independently: both group on the `(rule_id, finding_type)` pair, and a
shared derivation would make a defect in that key invisible -- the template
would emit wrongly-keyed citations, the check would resolve wrongly-keyed
citations, the two would agree and both would be wrong. The import graph is
walked rather than the independence promised, following `ai-007`, and the
walker is fired at `app.ai.providers.template`, which genuinely does import
the template.

**These run against bundles the real builder produced**, per the rule
`evb-002` and `ai-002` both learned: a hand-written `EvidenceBundle`
literal tests the author's model of a bundle rather than a bundle.

Three of these cannot fail against a permissive implementation and the
suite says so rather than leaving a reader to wonder. The two import-graph
guards are a membership test that is absent when it holds and absent when
it is broken, which is why each is preceded by a control -- one proving the
walker reaches what it claims, one firing it at a module that really does
import the template. The stored-status mapping is shape.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.ai.fallback import CorrectnessFallback, RefusalCategory
from app.ai.grounding import (
    CitationVerdict,
    GroundingChecker,
    GroundingLedger,
    NearMiss,
    check,
)
from app.ai.hypothesis import Citation, Hypothesis
from app.ai.providers.template import TemplateGenerator
from app.ai.service import GenerationRefused, GeneratorKind
from app.ai.template import generate
from app.db.hypotheses import GroundingStatus
from tests.test_ai_fallback import _ScriptedArm, model_result
from tests.test_ai_service import template_config
from tests.test_ai_template import (
    fault_bundle,
    kinds,
    superseded_fault_bundle,
    zone_bundle,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ the doubles


def citing(bundle, *pairs, statement="what the generator said about it"):
    """A real template hypothesis over `bundle`, its citations replaced.

    Everything else in the object stays as the template wrote it, so a test
    that changes one citation is changing one citation.
    """
    base = generate(bundle)
    citations = tuple(
        Citation(rule_id=rule_id, finding_type=finding_type, statement=statement)
        for rule_id, finding_type in pairs
    )
    return Hypothesis(**{**base.model_dump(), "supporting_evidence": citations})


def first_pair(bundle):
    """A `(rule_id, finding_type)` pair the bundle genuinely carries."""
    return kinds(bundle)[0]


def rule_with_several_types(bundle):
    """A rule id the bundle carries under more than one finding type."""
    by_rule: dict[str, list[str]] = {}
    for rule_id, finding_type in kinds(bundle):
        by_rule.setdefault(rule_id, []).append(finding_type)
    return next((rule, types) for rule, types in by_rule.items() if len(types) > 1)


def superseded_pair(bundle):
    """The `(rule_id, anomaly_type)` of the claim the ladder threw out."""
    claim = bundle.superseded[0]
    return (claim.rule_id, claim.anomaly_type)


def verdicts(report):
    return [finding.verdict for finding in report.findings]


def _broken_index(bundle):
    """A defect inside the check itself, for proving it is not laundered."""
    raise ZeroDivisionError("the grounding check is broken")


# -------------------------------------------------------- what grounded means


def test_a_citation_naming_a_pair_the_bundle_carries_is_grounded():
    # spec: ai-008 -- the whole check in one line. The bundle is the closed
    # list, and membership of it is what "grounded" means.
    bundle = fault_bundle()
    rule_id, finding_type = first_pair(bundle)

    report = check(citing(bundle, (rule_id, finding_type)), bundle)

    assert verdicts(report) == [CitationVerdict.GROUNDED]
    assert report.passed


def test_every_citation_of_a_template_hypothesis_over_a_fault_bundle_is_grounded():
    # spec: ai-008, ai-002 -- the oracle. The template copies everything it
    # writes out of the bundle, so its output is grounded by construction
    # and anything flagged here is a defect in this module.
    bundle = fault_bundle()

    report = check(generate(bundle), bundle)

    assert report.passed, report.reason
    assert set(verdicts(report)) == {CitationVerdict.GROUNDED}


def test_every_citation_of_a_template_hypothesis_over_a_zone_bundle_is_grounded():
    # spec: ai-008, ai-002 -- the same oracle over the bundle spanning both
    # data modes and four kinds of evidence, which is where a key derived
    # slightly wrongly would first show.
    bundle = zone_bundle()

    report = check(generate(bundle), bundle)

    assert report.passed, report.reason
    assert len(report.findings) == len(kinds(bundle))


def test_a_citation_naming_a_rule_the_bundle_does_not_carry_is_caught():
    # spec: ai-008 -- the item's own named failure case, verbatim.
    bundle = fault_bundle()

    report = check(citing(bundle, ("RF-NOISE-999", "rf_power_deviation")), bundle)

    assert verdicts(report) == [CitationVerdict.UNKNOWN]
    assert not report.passed


def test_a_real_rule_with_an_invented_finding_type_is_caught():
    # spec: ai-008, ai-001 -- the pair is the identity and the rule alone is
    # not. A check resolving the rule id only would pass this, and would
    # then pass anom-012's rate excess cited as anom-010's discontinuity,
    # which is the confusion the two-identifier citation exists to catch.
    bundle = fault_bundle()
    rule_id, _ = first_pair(bundle)

    report = check(citing(bundle, (rule_id, "a_finding_type_nobody_emits")), bundle)

    assert verdicts(report) == [CitationVerdict.UNKNOWN]


def test_a_real_finding_type_under_the_wrong_rule_is_caught():
    # spec: ai-008 -- the other half of the pair, so neither identifier can
    # be the one that is silently ignored.
    bundle = fault_bundle()
    _, finding_type = first_pair(bundle)

    report = check(citing(bundle, ("A-RULE-THAT-NEVER-RAN", finding_type)), bundle)

    assert verdicts(report) == [CitationVerdict.UNKNOWN]


def test_one_bad_citation_among_good_ones_is_the_one_caught():
    # spec: ai-008 -- a check judging the hypothesis as a whole could not
    # say which claim to investigate, and eval-005 counts claims.
    bundle = zone_bundle()
    good, other = kinds(bundle)[0], kinds(bundle)[1]

    report = check(citing(bundle, good, ("INVENTED", "invented"), other), bundle)

    assert verdicts(report) == [
        CitationVerdict.GROUNDED,
        CitationVerdict.UNKNOWN,
        CitationVerdict.GROUNDED,
    ]
    assert [f.position for f in report.ungrounded] == [2]


def test_the_statement_beside_a_citation_is_not_resolved():
    # spec: ai-008 -- the stated limitation, asserted so it is a property of
    # the item rather than a surprise. Only the two identifiers are
    # resolvable; whether the sentence is *true of* the finding it names is
    # eval-004's scoring and no part of this.
    bundle = fault_bundle()
    pair = first_pair(bundle)

    report = check(
        citing(bundle, pair, statement="the receiver was struck by lightning"), bundle
    )

    assert report.passed


def test_two_citations_of_the_same_pair_are_both_grounded():
    # spec: ai-008 -- the check resolves citations, it does not police
    # duplication. Collapsing them would make one finding stand for two
    # claims and undercount eval-005's denominator.
    bundle = fault_bundle()
    pair = first_pair(bundle)

    report = check(citing(bundle, pair, pair), bundle)

    assert verdicts(report) == [CitationVerdict.GROUNDED, CitationVerdict.GROUNDED]


# -------------------------------------------------- the superseded compartment


def test_a_citation_of_a_superseded_claim_is_refused():
    # spec: ai-008, evb-001, anom-013 -- the amendment's failure case. The
    # identifier does resolve, which is exactly why a membership test over
    # the whole bundle would certify the error it exists to catch.
    bundle = superseded_fault_bundle()

    report = check(citing(bundle, superseded_pair(bundle)), bundle)

    assert not report.passed


def test_a_superseded_citation_is_not_merely_unknown():
    # spec: ai-008 -- the two must not merge. An invented identifier is a
    # model hallucinating a name; a superseded citation is a model
    # misreading the bundle it was handed, reading two rules' disagreement
    # as two rules' agreement. The second is the more alarming, and a single
    # verdict would lose it.
    bundle = superseded_fault_bundle()

    report = check(citing(bundle, superseded_pair(bundle)), bundle)

    assert verdicts(report) == [CitationVerdict.SUPERSEDED]


def test_the_superseded_claim_really_is_present_in_the_bundle():
    # spec: ai-008 -- the differential. The test above is satisfied by a
    # check refusing any citation at all, so the thing being refused has to
    # be shown genuinely in the bundle and genuinely absent from the
    # evidence list.
    bundle = superseded_fault_bundle()
    rule_id, anomaly_type = superseded_pair(bundle)

    assert (rule_id, anomaly_type) not in kinds(bundle)
    assert any(c.rule_id == rule_id for c in bundle.superseded)


def test_a_pair_absent_from_a_bundle_with_no_superseded_field_is_unknown():
    # spec: ai-008 -- the superseded verdict is reached by looking, not by
    # being the default for anything that fails to resolve.
    bundle = fault_bundle()

    report = check(citing(bundle, ("SOURCE-GAP", "possible_data_source_issue")), bundle)

    assert bundle.superseded == ()
    assert verdicts(report) == [CitationVerdict.UNKNOWN]


def test_a_superseded_rule_with_a_finding_type_nobody_has_is_unknown():
    # spec: ai-008 -- the verdict describes the pair that was cited, not the
    # rule it mentions. A rejected claim is a specific claim.
    bundle = superseded_fault_bundle()
    rule_id, _ = superseded_pair(bundle)

    report = check(citing(bundle, (rule_id, "something_else_entirely")), bundle)

    assert verdicts(report) == [CitationVerdict.UNKNOWN]


def test_evidence_wins_when_a_pair_sits_in_both_compartments():
    # spec: ai-008 -- ordering, stated. A pair present in the evidence list
    # is citable whatever else the bundle records, so the sharper verdict is
    # reached only when the pair is genuinely absent from the evidence.
    bundle = superseded_fault_bundle()
    rule_id, anomaly_type = superseded_pair(bundle)
    borrowed = dataclasses.replace(
        bundle.evidence[0], rule_id=rule_id, finding_type=anomaly_type
    )
    widened = bundle.with_evidence([*bundle.evidence, borrowed])

    report = check(citing(widened, (rule_id, anomaly_type)), widened)

    assert widened.superseded == bundle.superseded
    assert verdicts(report) == [CitationVerdict.GROUNDED]


def test_the_bundles_own_rule_id_is_not_citable_on_its_own():
    # spec: ai-008 -- only the evidence list is citable. Citing the claim as
    # support for itself is circular, and the top-level rule id is metadata
    # about the claim rather than an item of evidence.
    bundle = zone_bundle()

    report = check(citing(bundle, (bundle.rule_id, "the_claim_itself")), bundle)

    assert verdicts(report) == [CitationVerdict.UNKNOWN]


# ------------------------------------------------------------- the near misses


def test_a_rule_cited_under_the_wrong_one_of_its_own_finding_types_near_misses():
    # spec: ai-008 -- the most likely genuine model error, and the one the
    # pair was introduced to catch. Counted with outright invention, a catch
    # rate says nothing about what went wrong.
    bundle = fault_bundle()
    rule_id, _ = rule_with_several_types(bundle)

    report = check(citing(bundle, (rule_id, "not_a_type_this_rule_emits")), bundle)

    assert report.findings[0].near_miss is NearMiss.RULE_ID_UNDER_ANOTHER_TYPE


def test_a_near_miss_does_not_soften_the_verdict():
    # spec: ai-008 -- the near miss is reporting, never mitigation. A
    # citation that nearly resolved did not resolve.
    bundle = fault_bundle()
    rule_id, _ = rule_with_several_types(bundle)

    report = check(citing(bundle, (rule_id, "not_a_type_this_rule_emits")), bundle)

    assert verdicts(report) == [CitationVerdict.UNKNOWN]
    assert not report.passed


def test_the_near_miss_detail_names_the_finding_types_that_are_present():
    # spec: ai-008 -- what makes the near miss worth recording at all: the
    # reader is told what the rule actually emitted, which is the whole
    # difference between an investigable catch and a count.
    bundle = fault_bundle()
    rule_id, types = rule_with_several_types(bundle)

    report = check(citing(bundle, (rule_id, "not_a_type_this_rule_emits")), bundle)

    for finding_type in types:
        assert finding_type in report.findings[0].detail


def test_a_citation_differing_only_in_case_is_refused():
    # spec: ai-008 -- matching is exact. Normalising would silently repair
    # model output and understate a catch rate eval-005 reports as a result.
    bundle = fault_bundle()
    rule_id, finding_type = first_pair(bundle)
    assert (rule_id.lower(), finding_type.upper()) != (rule_id, finding_type)

    report = check(citing(bundle, (rule_id.lower(), finding_type.upper())), bundle)

    assert verdicts(report) == [CitationVerdict.UNKNOWN]


def test_a_citation_differing_only_in_case_is_recorded_as_a_near_miss():
    # spec: ai-008 -- refused and recorded, because "14 catches" and "14
    # catches, 11 of them spelling" are different findings and only the
    # second says anything.
    bundle = fault_bundle()
    rule_id, finding_type = first_pair(bundle)

    report = check(citing(bundle, (rule_id.lower(), finding_type.upper())), bundle)

    assert report.findings[0].near_miss is NearMiss.CASE_OR_SPACING


def test_a_citation_differing_only_in_interior_space_is_a_near_miss():
    # spec: ai-008 -- the same class of slip. The schema already strips a
    # citation's edges, so this is an interior difference and not a stray
    # leading space a validator would have removed.
    bundle = fault_bundle()
    rule_id, finding_type = first_pair(bundle)
    spaced = rule_id.replace("-", " - ")
    assert spaced != rule_id

    report = check(citing(bundle, (spaced, finding_type)), bundle)

    assert report.findings[0].verdict is CitationVerdict.UNKNOWN
    assert report.findings[0].near_miss is NearMiss.CASE_OR_SPACING


def test_the_spelling_near_miss_is_preferred_over_the_rule_id_one():
    # spec: ai-008 -- both apply when a rule carrying several finding types
    # is cited with one of them miscapitalised, and the specific reading is
    # the useful one. An arbitrary order here would report a spelling slip
    # as a rule confusion and invert what the measurement says.
    bundle = fault_bundle()
    rule_id, types = rule_with_several_types(bundle)
    assert types[0].upper() != types[0]

    report = check(citing(bundle, (rule_id, types[0].upper())), bundle)

    assert report.findings[0].near_miss is NearMiss.CASE_OR_SPACING


def test_a_grounded_citation_carries_no_near_miss_and_no_detail():
    # spec: ai-008 -- nothing to explain about a citation that resolved, and
    # a detail on every finding would make the failing ones unfindable by
    # eye in a log.
    bundle = fault_bundle()

    report = check(citing(bundle, first_pair(bundle)), bundle)

    assert report.findings[0].near_miss is None
    assert report.findings[0].detail == ""


def test_an_entirely_invented_citation_carries_no_near_miss():
    # spec: ai-008 -- the differential for the near-miss tests above, which
    # a checker marking everything a near miss would otherwise satisfy.
    bundle = fault_bundle()

    report = check(citing(bundle, ("NOTHING-LIKE-IT", "nor_this")), bundle)

    assert report.findings[0].near_miss is None
    assert report.findings[0].verdict is CitationVerdict.UNKNOWN


def test_a_superseded_claim_cited_with_the_wrong_case_still_near_misses():
    # spec: ai-008 -- a spelling slip must not hide which compartment was
    # reached for. The verdict stays unknown, because matching is exact, but
    # the record says the model was reaching for a rejected claim.
    bundle = superseded_fault_bundle()
    rule_id, anomaly_type = superseded_pair(bundle)

    report = check(citing(bundle, (rule_id.lower(), anomaly_type)), bundle)

    assert report.findings[0].verdict is CitationVerdict.UNKNOWN
    assert report.findings[0].near_miss is NearMiss.CASE_OR_SPACING
    assert "reject" in report.findings[0].detail


# ------------------------------------------------------------------ the report


def test_one_ungrounded_citation_fails_the_whole_report():
    # spec: ai-008, FR-512 -- a hypothesis resting partly on something
    # invented is not partly acceptable, and ai-007 throws the whole attempt
    # away.
    bundle = zone_bundle()

    report = check(citing(bundle, first_pair(bundle), ("MADE-UP", "made_up")), bundle)

    assert not report.passed


def test_there_is_one_finding_per_citation_in_citation_order():
    # spec: ai-008 -- per-item determinations, and the order is the
    # hypothesis's own so a position in a message points at the citation an
    # analyst is reading.
    bundle = zone_bundle()
    pairs = [kinds(bundle)[0], ("X-ONE", "x_one"), kinds(bundle)[1], ("X-TWO", "x_two")]

    report = check(citing(bundle, *pairs), bundle)

    assert [(f.rule_id, f.finding_type) for f in report.findings] == pairs
    assert [f.position for f in report.findings] == [1, 2, 3, 4]


def test_the_ungrounded_list_holds_only_the_failures():
    # spec: ai-008 -- what eval-005 counts and what an investigation opens.
    bundle = zone_bundle()
    pairs = [kinds(bundle)[0], ("X-ONE", "x_one"), ("X-TWO", "x_two")]

    report = check(citing(bundle, *pairs), bundle)

    assert [(f.rule_id, f.finding_type) for f in report.ungrounded] == pairs[1:]


def test_the_reason_names_every_failing_citation_and_its_position():
    # spec: ai-008 -- this string is what ai-007 records on the refusal and
    # logs, and a reason that does not say which claim failed leaves the
    # investigation to start from the whole hypothesis.
    bundle = zone_bundle()
    pairs = [kinds(bundle)[0], ("X-ONE", "x_one"), ("X-TWO", "x_two")]

    reason = check(citing(bundle, *pairs), bundle).reason

    assert "X-ONE" in reason and "x_one" in reason
    assert "X-TWO" in reason and "x_two" in reason
    assert "citation 2" in reason and "citation 3" in reason
    assert "citation 1" not in reason


def test_the_reason_distinguishes_a_rejected_claim_from_an_invented_one():
    # spec: ai-008 -- the two verdicts are kept apart in the object and must
    # stay apart in the sentence a human reads, or the distinction exists
    # only where nobody looks.
    bundle = superseded_fault_bundle()

    invented = check(citing(bundle, ("NOT-A-RULE", "nope")), bundle).reason
    rejected = check(citing(bundle, superseded_pair(bundle)), bundle).reason

    assert "reject" in rejected
    assert "reject" not in invented


def test_a_passing_report_has_nothing_to_say():
    # spec: ai-008 -- a reason on a passing report would be logged beside
    # every successful generation and read as a warning.
    bundle = fault_bundle()

    assert check(generate(bundle), bundle).reason == ""


def test_a_report_maps_onto_the_stored_three_valued_grounding_status():
    # spec: ai-008, db-002 -- cannot fail against a permissive
    # implementation; it is shape. db-002's column is three-valued because a
    # hypothesis is written before this runs, so a report can only ever
    # produce two of the three and not_checked is not something this module
    # can emit.
    bundle = fault_bundle()

    passed = check(generate(bundle), bundle)
    failed = check(citing(bundle, ("NOT-A-RULE", "nope")), bundle)

    assert GroundingStatus.from_stored(passed.passed) is GroundingStatus.PASSED
    assert GroundingStatus.from_stored(failed.passed) is GroundingStatus.FAILED


# ------------------------------------------------- the surface ai-007 injects


def test_the_checker_returns_nothing_when_the_hypothesis_is_grounded():
    # spec: ai-008, ai-007 -- the injected check's contract: raise or
    # return. A bool would make "ungrounded" and "the check itself failed"
    # the same answer.
    bundle = fault_bundle()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED)

    assert checker(generate(bundle), bundle) is None


def test_the_checker_raises_a_generation_refusal_when_it_is_not():
    # spec: ai-008, ai-007 -- GenerationRefused specifically, because ai-007
    # tells its two refusal categories apart by origin and this is what
    # makes a refusal from here ungrounded rather than malformed.
    bundle = fault_bundle()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED)

    with pytest.raises(GenerationRefused):
        checker(citing(bundle, ("NOT-A-RULE", "nope")), bundle)


def test_the_raised_refusal_carries_the_reports_reason():
    # spec: ai-008 -- ai-007 stores this string on the refusal and logs it,
    # so a refusal saying only "ungrounded" costs the investigation the one
    # fact it needed.
    bundle = fault_bundle()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED)

    with pytest.raises(GenerationRefused) as raised:
        checker(citing(bundle, ("NOT-A-RULE", "nope")), bundle)

    assert "NOT-A-RULE" in str(raised.value)
    assert "citation 1" in str(raised.value)


def test_a_fault_inside_the_check_is_not_reported_as_the_model_being_ungrounded(
    monkeypatch,
):
    # spec: ai-008, ai-007 -- the ai-007 mutation pass found nothing made
    # the injected check raise anything but a refusal, so a defect in this
    # module would have been recorded as the model citing something unreal,
    # inflating a reported evaluation result with the checker's own fault.
    # An internal failure surfaces as itself.
    monkeypatch.setattr("app.ai.grounding._citable_index", _broken_index)
    bundle = fault_bundle()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED)

    with pytest.raises(ZeroDivisionError):
        checker(generate(bundle), bundle)


def test_wired_into_the_fallback_a_grounded_hypothesis_is_returned_unchanged():
    # spec: ai-008, ai-007 -- composed with the thing that injects it,
    # rather than only against its own signature.
    bundle = fault_bundle()
    hypothesis = generate(bundle)
    arm = _ScriptedArm(model_result(hypothesis=hypothesis))
    fallback = CorrectnessFallback(
        arm,
        TemplateGenerator(template_config()),
        check=GroundingChecker(arm=GeneratorKind.HOSTED),
        max_attempts=2,
    )

    outcome = fallback.generate_recorded(bundle)

    assert outcome.fell_back is False
    assert outcome.refusals == ()
    assert outcome.result.hypothesis == hypothesis


def test_wired_in_an_ungrounded_hypothesis_is_recorded_as_ungrounded():
    # spec: ai-008, ai-007 -- the category matters: malformed means the
    # provider broke its own schema guarantee, ungrounded means it parsed
    # and then cited something unreal, and db-002 stores the second as a row
    # and the first as nothing at all.
    bundle = fault_bundle()
    bad = citing(bundle, ("NOT-A-RULE", "nope"))
    arm = _ScriptedArm(model_result(hypothesis=bad), model_result(hypothesis=bad))
    fallback = CorrectnessFallback(
        arm,
        TemplateGenerator(template_config()),
        check=GroundingChecker(arm=GeneratorKind.HOSTED),
        max_attempts=2,
    )

    outcome = fallback.generate_recorded(bundle)

    assert [r.category for r in outcome.refusals] == [
        RefusalCategory.UNGROUNDED,
        RefusalCategory.UNGROUNDED,
    ]
    assert outcome.fell_back is True


def test_the_template_the_fallback_reaches_for_passes_the_same_check():
    # spec: ai-008, ai-002, ai-007 -- end to end, and the point of the whole
    # arrangement: the analyst reads something this check would pass.
    bundle = zone_bundle()
    bad = citing(bundle, ("NOT-A-RULE", "nope"))
    fallback = CorrectnessFallback(
        _ScriptedArm(model_result(hypothesis=bad)),
        TemplateGenerator(template_config()),
        check=GroundingChecker(arm=GeneratorKind.HOSTED),
        max_attempts=1,
    )

    outcome = fallback.generate_recorded(bundle)

    assert outcome.fell_back is True
    assert check(outcome.result.hypothesis, bundle).passed


# ---------------------------------------------------- the ledger, and the rate


def test_a_hypothesis_that_passed_is_checked_but_not_caught():
    # spec: ai-008 -- the denominator and the numerator are different
    # counts, and a catch rate needs both.
    bundle = fault_bundle()
    ledger = GroundingLedger()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger)

    checker.report(generate(bundle), bundle)

    assert ledger.checked(GeneratorKind.HOSTED) == 1
    assert ledger.caught(GeneratorKind.HOSTED) == 0


def test_a_hypothesis_that_failed_is_both_checked_and_caught():
    # spec: ai-008 -- a catch is a check that failed, not a separate event.
    bundle = fault_bundle()
    ledger = GroundingLedger()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger)

    checker.report(citing(bundle, ("NOT-A-RULE", "nope")), bundle)

    assert ledger.checked(GeneratorKind.HOSTED) == 1
    assert ledger.caught(GeneratorKind.HOSTED) == 1


def test_the_catch_rate_is_the_caught_over_the_checked():
    # spec: ai-008, eval-005 -- the reportable result this item exists to
    # produce, not merely a safety net.
    bundle = fault_bundle()
    ledger = GroundingLedger()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger)

    checker.report(generate(bundle), bundle)
    checker.report(generate(bundle), bundle)
    checker.report(citing(bundle, ("NOT-A-RULE", "nope")), bundle)
    checker.report(citing(bundle, ("NOR-THIS", "nope")), bundle)

    assert ledger.catch_rate(GeneratorKind.HOSTED) == 0.5


def test_an_arm_that_was_never_checked_has_no_catch_rate_rather_than_zero():
    # spec: ai-008 -- the amendment's second pin. Never-caught-anything and
    # never-ran must not arrive identically: the write-up sentence "the
    # check flagged nothing on the template arm" is false in exactly the
    # case where the template arm was never put through it.
    ledger = GroundingLedger()

    assert ledger.catch_rate(GeneratorKind.TEMPLATE) is None
    assert ledger.checked(GeneratorKind.TEMPLATE) == 0


def test_an_unmeasured_rate_is_distinguishable_from_a_measured_zero():
    # spec: ai-008 -- the differential, and the only thing making the test
    # above mean anything. A measured zero is a result.
    bundle = fault_bundle()
    ledger = GroundingLedger()
    GroundingChecker(arm=GeneratorKind.TEMPLATE, ledger=ledger).report(
        generate(bundle), bundle
    )

    assert ledger.catch_rate(GeneratorKind.TEMPLATE) == 0.0
    assert ledger.catch_rate(GeneratorKind.HOSTED) is None


def test_the_two_arms_are_counted_separately():
    # spec: ai-008, eval-005 -- a rate pooled across arms answers no
    # question the campaign asks.
    bundle = fault_bundle()
    ledger = GroundingLedger()
    GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger).report(
        citing(bundle, ("NOT-A-RULE", "nope")), bundle
    )
    GroundingChecker(arm=GeneratorKind.TEMPLATE, ledger=ledger).report(
        generate(bundle), bundle
    )

    assert ledger.catch_rate(GeneratorKind.HOSTED) == 1.0
    assert ledger.catch_rate(GeneratorKind.TEMPLATE) == 0.0


def test_the_arm_is_the_declared_one_and_not_read_from_the_hypothesis():
    # spec: ai-008, ai-009 -- a hypothesis carries no record of what
    # produced it, which is why the arm is declared where the check is wired
    # in. The same argument ai-009 settled for a refused call.
    bundle = fault_bundle()
    ledger = GroundingLedger()

    GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger).report(
        generate(bundle), bundle
    )

    assert ledger.checked(GeneratorKind.HOSTED) == 1
    assert ledger.checked(GeneratorKind.TEMPLATE) == 0


def test_ordinals_run_through_the_ledger_across_arms():
    # spec: ai-008 -- one ledger spans a run, so the ordinal is the position
    # in that run and not in one arm's share of it.
    bundle = fault_bundle()
    ledger = GroundingLedger()
    hosted = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger)
    local = GroundingChecker(arm=GeneratorKind.LOCAL, ledger=ledger)

    hosted.report(generate(bundle), bundle)
    local.report(generate(bundle), bundle)
    hosted.report(generate(bundle), bundle)

    assert [r.ordinal for r in ledger.records] == [1, 2, 3]
    assert [r.arm for r in ledger.records] == [
        GeneratorKind.HOSTED,
        GeneratorKind.LOCAL,
        GeneratorKind.HOSTED,
    ]


def test_the_ledger_hands_out_a_snapshot_and_not_its_live_list():
    # spec: ai-008 -- a caller holding the live list sees a ledger that
    # changes under it, which ai-009 records for the same reason.
    bundle = fault_bundle()
    ledger = GroundingLedger()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger)
    checker.report(generate(bundle), bundle)

    held = ledger.records
    checker.report(generate(bundle), bundle)

    assert len(held) == 1
    assert len(ledger.records) == 2


def test_near_misses_are_retrievable_per_arm():
    # spec: ai-008, eval-005 -- what makes a catch rate interpretable: how
    # many of the catches were one rule's findings mistaken for another's.
    bundle = fault_bundle()
    rule_id, _ = rule_with_several_types(bundle)
    ledger = GroundingLedger()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger)

    checker.report(citing(bundle, (rule_id, "not_a_type_this_rule_emits")), bundle)
    checker.report(citing(bundle, ("NOTHING-LIKE-IT", "nor_this")), bundle)

    near = ledger.near_misses(GeneratorKind.HOSTED)

    assert [f.near_miss for f in near] == [NearMiss.RULE_ID_UNDER_ANOTHER_TYPE]


def test_a_checker_without_a_ledger_still_reports():
    # spec: ai-008 -- the gate and the measurement are separate jobs, and a
    # deployment wanting only the gate must not have to hold a ledger it
    # never reads.
    bundle = fault_bundle()

    report = GroundingChecker(arm=GeneratorKind.HOSTED).report(generate(bundle), bundle)

    assert report.passed


def test_the_raising_surface_records_into_the_ledger_too():
    # spec: ai-008 -- ai-007 only ever calls the raising surface, so a
    # ledger fed only by the reporting one would record nothing at all in
    # the arrangement the campaign actually runs.
    bundle = fault_bundle()
    ledger = GroundingLedger()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger)

    with pytest.raises(GenerationRefused):
        checker(citing(bundle, ("NOT-A-RULE", "nope")), bundle)

    assert ledger.caught(GeneratorKind.HOSTED) == 1


def test_each_hypothesis_is_recorded_once_and_not_once_per_citation():
    # spec: ai-008 -- the unit of a catch rate is a hypothesis. Counting
    # citations would make a hypothesis citing six kinds weigh six times
    # what one citing a single kind weighs.
    bundle = zone_bundle()
    ledger = GroundingLedger()
    checker = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger)

    checker.report(citing(bundle, ("A", "a"), ("B", "b"), ("C", "c")), bundle)

    assert ledger.checked(GeneratorKind.HOSTED) == 1
    assert ledger.caught(GeneratorKind.HOSTED) == 1


# ------------------------------------------ the oracle must not share the fault


def app_modules_reached(module: str) -> set[str]:
    """Every `app.*` module reachable from `module` through app source.

    Deliberately not `ai-002`'s walker, which collapses its answer to
    top-level names and so cannot see one app module reaching another.
    """
    seen: set[str] = set()
    queue = [module]

    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = BACKEND_ROOT / Path(*name.split(".")).with_suffix(".py")
        if not path.is_file():
            path = BACKEND_ROOT / Path(*name.split(".")) / "__init__.py"
        assert path.is_file(), f"cannot read {name} at {path}"

        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                targets = [node.module]
            for target in targets:
                if target.split(".")[0] == "app":
                    queue.append(target)
    return seen - {module}


def test_the_module_walker_reaches_what_it_claims_to():
    # spec: ai-008 -- the two guards below pass vacuously against a walker
    # returning nothing, which is the shape of wrong test this project has
    # now written twice and ai-002 records.
    reached = app_modules_reached("app.ai.grounding")

    assert "app.ai.hypothesis" in reached
    assert "app.detection.bundle" in reached


def test_the_module_walker_catches_a_module_that_does_import_the_template():
    # spec: ai-008 -- the interlock fired at a real positive rather than
    # only at the case it must pass. app.ai.providers.template genuinely
    # puts ai-002 behind the port, so a walker that cannot see that cannot
    # see anything.
    assert "app.ai.template" in app_modules_reached("app.ai.providers.template")


def test_the_grounding_check_does_not_reach_the_generator_that_validates_it():
    # spec: ai-008, ai-002 -- the oracle argument. Both group citations on
    # the (rule_id, finding_type) pair, so a shared derivation would make a
    # defect in that key invisible: the template would emit wrongly-keyed
    # citations, this would resolve wrongly-keyed citations, the two would
    # agree and both would be wrong. A comment saying so holds only while
    # everyone reads it.
    assert "app.ai.template" not in app_modules_reached("app.ai.grounding")


def test_the_grounding_check_does_not_reach_the_persistence_layer():
    # spec: ai-008, db-002 -- the three-valued status is mapped at the write
    # boundary and not here. Reaching it would put SQLAlchemy in the path of
    # every generated hypothesis for the sake of one enum.
    assert "app.db.hypotheses" not in app_modules_reached("app.ai.grounding")


# ---------------------------------------------------------------- determinism


def test_the_report_does_not_depend_on_the_hash_seed():
    # spec: ai-008, NFR-601 -- set and dict-of-string iteration order varies
    # with PYTHONHASHSEED between processes, and an unordered collection in
    # an output path is how this repository has produced a result differing
    # between runs three times. The near-miss detail lists the finding types
    # a rule carries, which is exactly such a path.
    script = (
        "from app.ai.grounding import check\n"
        "from tests.test_ai_grounding import citing, rule_with_several_types\n"
        "from tests.test_ai_template import fault_bundle\n"
        "b = fault_bundle()\n"
        "rule_id, _ = rule_with_several_types(b)\n"
        "print(check(citing(b, (rule_id, 'nope'), ('X', 'x')), b).reason)\n"
    )

    def run(seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(BACKEND_ROOT)}
        done = subprocess.run(
            [sys.executable, "-c", script],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout

    assert run("0") == run("12345")
