"""The template hypothesis generator. Spec: ai-002.

The first thing in the project that produces an explanation, and the one
with no model in it. It reads an evidence bundle and writes the hypothesis
out by rule, the same way every time.

It has two jobs and both are load-bearing, which is what most of this
suite is really about.

**It is the correctness fallback.** When a model arm returns something that
fails validation or fails the grounding check, this is what the analyst
gets instead of an error. A fallback that shares a dependency with the
thing that failed is not a fallback, so the independence is asserted from
the import graph rather than promised in a comment.

**It is the evaluation baseline.** The research question is whether a
language model adds anything over an honest mechanical summary of the same
evidence, and that question has no answer without the honest mechanical
summary to compare against. The campaign scores this blind alongside the
model arms, so it must be good enough to hand an analyst and plain enough
that it cannot flatter itself.

Everything it emits is copied from the bundle, so a template hypothesis is
grounded by construction -- which makes it a test of `ai-008` rather than
of this generator: anything the grounding check flags on a template
hypothesis is a defect in the check.

**Nine of these cannot fail against a permissive stub, and the suite says
so rather than leaving a reader to wonder.** Measured, not assumed: a
throwaway stub returning a fixed valid hypothesis passed eleven of the
first draft, and four of those were wrong tests that have been strengthened
-- an absence assertion satisfied by citing nothing real, the superseded
failure case satisfied the same way, and an action check satisfied by the
words "Check it.". The nine that remain are so by nature. The positive
confidence case passes against a constant `High` and is made load-bearing
by the differential immediately after it; schema revalidation, the
no-ground-truth check and the three determinism tests are shape or
negative-space checks any well-formed output satisfies. The three
import-graph tests are the interesting case: the guard is a set
intersection that is empty when it holds and empty when it is broken, so
it is paired with one test proving the walker reaches what it claims and
one firing it at a module that really does reach the network.

**These tests run against bundles the real builder produced**, using
`evb-001`'s own helpers rather than hand-written `EvidenceBundle` literals.
That is deliberate and it is the second time this project has needed the
rule: `evb-002`'s first draft asserted ref shapes against the test file's
own helpers and passed before the implementation existed, because it was
testing the author's model of a bundle rather than a bundle.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from app.ai.hypothesis import Confidence, Hypothesis
from app.ai.template import TemplateError, generate
from app.detection.baseline import RfCell
from app.detection.fusion import ANOMALY_TYPE as ZONE_TYPE
from app.detection.fusion import Corroboration
from app.detection.precedence import Claim, Suppression
from app.detection.rf_noise import RfNoiseFindings, UnjudgedCell
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT_TYPE

# The real builder's fixtures. See the module docstring: a bundle made here
# would be a bundle as this file imagines one.
from tests.test_evb_bundle import (
    START,
    WHY,
    build,
    claim_for,
    episode,
    fault,
    track_finding,
    zone,
)


def fault_bundle(**kw):
    """A `possible_sensor_fault` bundle, straight from the real builder."""
    f = fault(**kw)
    rf = RfNoiseFindings(anomalies=(episode("RF-03", 4),))
    return build([claim_for(f)], faults=[f], rf=rf)[0]


def zone_bundle(*, tracks=True, suppressed=(), **kw):
    """A `possible_interference_zone` bundle spanning both data modes."""
    z = zone(**kw)
    rf = RfNoiseFindings(anomalies=(episode("RF-03", 4), episode("RF-04", 4)))
    later = START + timedelta(seconds=30)
    track_findings = (
        [track_finding(), track_finding("AC-aaaa1111", at=later)] if tracks else []
    )
    return build(
        [claim_for(z)], zones=[z], rf=rf, tracks=track_findings, suppressed=suppressed
    )[0]


def kinds(bundle):
    """The distinct (rule_id, finding_type) pairs a bundle carries."""
    seen = []
    for item in bundle.evidence:
        pair = (item.rule_id, item.finding_type)
        if pair not in seen:
            seen.append(pair)
    return seen


def verdict_of(bundle):
    """The item carrying the bundle's own conclusion."""
    return next(i for i in bundle.evidence if i.finding_type == bundle.anomaly_type)


def rewrite_verdict(bundle, **details):
    """The same bundle with its verdict item's details replaced."""
    verdict = verdict_of(bundle)
    return bundle.with_evidence(
        [
            replace(item, details=details) if item is verdict else item
            for item in bundle.evidence
        ]
    )


# ------------------------------------------------- grounded by construction


def test_every_citation_names_a_pair_the_bundle_actually_carries():
    # spec: ai-002 -- the named failure case. A claim absent from the
    # bundle does not merely make one hypothesis wrong, it invalidates the
    # baseline the whole campaign is measured against.
    bundle = zone_bundle()
    available = set(kinds(bundle))

    cited = {(c.rule_id, c.finding_type) for c in generate(bundle).supporting_evidence}

    assert cited <= available
    assert cited == available


def test_a_kind_absent_from_the_bundle_is_never_cited():
    # spec: ai-002 -- the differential half of the test above. A generator
    # emitting a fixed list of citations would satisfy "every pair exists"
    # on a bundle that happens to carry all of them.
    fault_only = fault_bundle()

    hypothesis = generate(fault_only)
    cited = {c.rule_id for c in hypothesis.supporting_evidence}

    assert "TRACK-GAP" not in cited
    assert "FUSION-SPATIAL" not in cited
    # Absence alone is satisfied by a generator that cites nothing real, so
    # the positive half belongs in the same test.
    assert {(c.rule_id, c.finding_type) for c in hypothesis.supporting_evidence} == set(
        kinds(fault_only)
    )


def test_one_citation_per_distinct_kind_not_one_per_item():
    # spec: ai-002 -- a real bundle carries 34 items of 4 kinds. One
    # citation per item is complete and unreadable; one per kind is both.
    bundle = zone_bundle()

    hypothesis = generate(bundle)

    assert len(bundle.evidence) > len(kinds(bundle))
    assert len(hypothesis.supporting_evidence) == len(kinds(bundle))


def test_grouping_is_on_the_pair_and_not_on_the_rule_alone():
    # spec: ai-002, ai-001 -- anom-012 defines no rule id and borrows
    # anom-010's, so a rate excess and a discontinuity are identical by
    # rule id while making different claims. This is the first consumer
    # where grouping on the rule alone would visibly collapse them.
    bundle = zone_bundle()

    track = [
        c for c in generate(bundle).supporting_evidence if c.rule_id == "TRACK-GAP"
    ]

    assert len(track) == 2
    assert {c.finding_type for c in track} == {
        "track_rate_excess",
        "track_discontinuity",
    }


def test_citations_follow_first_appearance_order_in_the_bundle():
    # spec: ai-002 -- deterministic, and the bundle's order is the order
    # the rules reasoned in. Sorting alphabetically would put the aircraft
    # side before the radio evidence that raised the event.
    bundle = zone_bundle()

    cited = [(c.rule_id, c.finding_type) for c in generate(bundle).supporting_evidence]

    assert cited == kinds(bundle)


def test_a_kind_with_one_item_copies_that_item_s_own_words():
    # spec: ai-002 -- the maximally grounded case: nothing is composed.
    bundle = zone_bundle(tracks=False)
    excess = next(i for i in bundle.evidence if i.finding_type == "track_rate_excess")

    cited = next(
        c
        for c in generate(bundle).supporting_evidence
        if c.finding_type == "track_rate_excess"
    )

    assert excess.finding in cited.statement


def test_a_kind_with_several_items_says_how_many_it_stands_for():
    # spec: ai-002 -- a citation standing for six episodes while reading
    # like one understates the evidence, which for a baseline is the
    # direction that matters.
    z = zone()
    two = build(
        [claim_for(z)],
        zones=[z],
        tracks=[],
        rf=RfNoiseFindings(anomalies=(episode("RF-03", 4), episode("RF-04", 4))),
    )[0]
    three = build(
        [claim_for(z)],
        zones=[z],
        tracks=[],
        rf=RfNoiseFindings(
            anomalies=(episode("RF-03", 4), episode("RF-04", 4), episode("RF-03", 5))
        ),
    )[0]

    def rf_statement(bundle):
        return next(
            c.statement
            for c in generate(bundle).supporting_evidence
            if c.finding_type == "rf_noise_deviation"
        )

    # The first episode is identical in both, so the statements can only
    # differ by what the citation says about the ones behind it -- but
    # these two differ in how many SOURCES they span as well, so the
    # inequality alone does not pin the count. Found by mutation.
    assert rf_statement(two) != rf_statement(three)
    assert "2 findings" in rf_statement(two)
    assert "3 findings" in rf_statement(three)


# ------------------------------------------------------- confidence, inherited


def test_confidence_is_the_deciding_rule_s_own_confidence():
    # spec: ai-002, FR-715 -- the rule's confidence was measured and argued
    # when that rule was built. A second scoring scheme here would
    # eventually disagree with the first, invisibly.
    bundle = fault_bundle()

    assert verdict_of(bundle).details["confidence"] == "high"
    assert generate(bundle).confidence is Confidence.HIGH


def test_a_less_confident_verdict_produces_a_less_confident_hypothesis():
    # spec: ai-002 -- the differential. A generator returning a constant
    # High passes the test above on every bundle the corpus produces,
    # because anom-007 and anom-005 both reach High on the staged runs.
    bundle = rewrite_verdict(fault_bundle(), confidence="medium")

    assert generate(bundle).confidence is Confidence.MEDIUM


def test_the_two_vocabularies_are_joined_by_name_not_by_capitalisation():
    # spec: ai-002 -- the detection layer spells it `low` and the schema
    # demands `Low`. A pass-through raises; `.title()` launders any word at
    # all into something that looks valid.
    bundle = rewrite_verdict(fault_bundle(), confidence="low")

    assert generate(bundle).confidence is Confidence.LOW


def test_an_unrecognised_confidence_word_is_refused_not_laundered():
    # spec: ai-002 -- `.title()` would turn "certain" into "Certain" and
    # only the schema would catch it, one layer too late and with a message
    # about an enum rather than about the bundle.
    bundle = rewrite_verdict(fault_bundle(), confidence="certain")

    with pytest.raises(TemplateError) as raised:
        generate(bundle)

    assert "certain" in str(raised.value)


def test_a_numeric_confidence_is_refused():
    # spec: ai-002, FR-715, NFR-203 -- never a percentage and never a
    # decimal, and a rule that produced one would be a defect upstream
    # that must not be silently rounded into a word here.
    bundle = rewrite_verdict(fault_bundle(), confidence=0.87)

    with pytest.raises(TemplateError):
        generate(bundle)


def test_a_verdict_carrying_no_confidence_is_refused_rather_than_defaulted():
    # spec: ai-002, evb-001 -- a default here is a claim about the
    # evidence that nothing measured. Low would understate a High verdict
    # and High would be an invention.
    bundle = rewrite_verdict(fault_bundle())

    with pytest.raises(TemplateError) as raised:
        generate(bundle)

    assert "confidence" in str(raised.value)


# ----------------------------------------------------------- exactly one verdict


def test_a_bundle_with_no_verdict_item_is_refused():
    # spec: ai-002 -- both builders emit exactly one item whose
    # finding_type is the bundle's own anomaly type. A third builder that
    # forgot would otherwise get a hypothesis with an invented confidence.
    bundle = fault_bundle()
    verdict = verdict_of(bundle)
    # The first remaining item is given a valid confidence on purpose. A
    # generator that quietly fell back to it would then succeed, where
    # against an ordinary bundle it would raise for a different reason and
    # this test would pass without having tested anything. Found by
    # mutation: that is exactly what the first version of it did.
    remaining = [i for i in bundle.evidence if i is not verdict]
    remaining[0] = replace(remaining[0], details={"confidence": "high"})
    without = bundle.with_evidence(remaining)

    with pytest.raises(TemplateError) as raised:
        generate(without)

    assert FAULT_TYPE in str(raised.value)


def test_a_bundle_with_two_verdict_items_is_refused():
    # spec: ai-002, evb-002 -- the same rule evb-002 applies to resolving a
    # citation: a lookup is a resolution only if it returns exactly one
    # row. Taking the first of two is the unordered-result failure this
    # repository has now recorded three times.
    bundle = fault_bundle()
    verdict = verdict_of(bundle)
    doubled = bundle.with_evidence([*bundle.evidence, replace(verdict)])

    with pytest.raises(TemplateError):
        generate(doubled)


# --------------------------------------------------------------- alternatives


def superseded_fault_bundle():
    """A fault bundle that took its zone from a competing claim."""
    f = fault()
    loser = Claim(
        rule_id="SOURCE-GAP",
        anomaly_type="possible_data_source_issue",
        zone=claim_for(f).zone,
    )
    return build(
        [claim_for(f)],
        faults=[f],
        rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)),
        suppressed=[Suppression(claim=loser, claimed_by="SENSOR-FAULT", reason=WHY)],
    )[0]


def test_a_superseded_claim_becomes_an_alternative_explanation():
    # spec: ai-002, anom-013 -- a claim the ladder suppressed IS a
    # competing conclusion, already recorded as one. Inventing alternatives
    # while ignoring the ones the system itself ruled out would be the
    # generator disagreeing with its own evidence.
    bundle = superseded_fault_bundle()

    alternatives = " ".join(generate(bundle).alternative_explanations)

    assert "SOURCE-GAP" in alternatives
    assert "possible_data_source_issue" in alternatives


def test_a_superseded_claim_names_why_it_was_set_aside():
    # spec: ai-002, evb-001 -- phrased as a resolved competition. Stated
    # bare it reads as a second independent flag on the same area, which
    # inverts the truth exactly.
    bundle = superseded_fault_bundle()

    alternatives = " ".join(generate(bundle).alternative_explanations)

    assert WHY in alternatives


def test_a_superseded_claim_is_never_cited_as_supporting_evidence():
    # spec: ai-002 -- the second named failure case, and the one the
    # bundle builder already refuses to make possible. A generator citing
    # it would undo that at the last step before an analyst reads it.
    bundle = superseded_fault_bundle()

    cited = {(c.rule_id, c.finding_type) for c in generate(bundle).supporting_evidence}

    assert "SOURCE-GAP" not in {rule for rule, _ in cited}
    # And everything the bundle DOES carry is cited, so this cannot be
    # satisfied by a generator that simply cites little.
    assert cited == set(kinds(bundle))


def test_a_fault_bundle_names_interference_as_the_standing_alternative():
    # spec: ai-002, ai-001 -- the floor of one is satisfiable rather than
    # decorative precisely because these two are each other's competing
    # conclusion.
    alternatives = " ".join(generate(fault_bundle()).alternative_explanations)

    assert ZONE_TYPE in alternatives


def test_an_interference_bundle_names_a_receiver_fault_as_the_alternative():
    # spec: ai-002 -- the mirror. Together these two prove the alternative
    # is chosen from the bundle rather than printed from a constant.
    alternatives = " ".join(generate(zone_bundle()).alternative_explanations)

    assert FAULT_TYPE in alternatives


def test_every_hypothesis_carries_the_outside_the_ruleset_caveat_last():
    # spec: ai-002 -- the deterministic rules can only choose among the
    # conclusions they encode, which is true of every bundle and is exactly
    # the caveat a fluent generator omits. Last, so it reads as the
    # standing limit rather than as a finding about this event.
    bundles = (fault_bundle(), zone_bundle(), superseded_fault_bundle())
    last = {generate(b).alternative_explanations[-1] for b in bundles}

    # One string, identical across three different kinds of bundle: the
    # standing caveat and nothing else can be last. Asserting a word
    # instead let the caveat move to the front unnoticed, because the
    # type-specific alternative that took its place also says "rule".
    assert len(last) == 1
    assert "does not encode" in last.pop()
    for bundle in bundles:
        assert len(generate(bundle).alternative_explanations) >= 2


# --------------------------------------------------------- uncertainties, whole


def test_every_known_uncertainty_reaches_the_hypothesis():
    # spec: ai-002, evb-001 -- untruncated. Dropping the tail to keep the
    # text short loses the distinction between measured-and-negative and
    # never-looked, which is the material this layer exists to preserve.
    # Deliberately many: a bundle carrying one or two cannot catch a
    # generator that keeps the first three and drops the rest.
    f = fault()
    rf = RfNoiseFindings(
        anomalies=(episode("RF-03", 4),),
        unjudged=tuple(
            UnjudgedCell(
                cell=RfCell(sensor_id="RF-03", channel_index=c), reason="no baseline"
            )
            for c in (1, 2, 5, 6, 7)
        ),
    )
    bundle = build([claim_for(f)], faults=[f], rf=rf)[0]

    against = generate(bundle).evidence_against_or_uncertainty

    assert len(bundle.known_uncertainties) == 6
    assert len(against) == len(bundle.known_uncertainties)


def test_uncertainties_are_copied_verbatim_and_in_bundle_order():
    # spec: ai-002 -- the statements are already written out in prose that
    # carries which kind of not-knowing each one is, so copying is both the
    # most faithful option and the one that composes nothing.
    rf = RfNoiseFindings(
        anomalies=(episode("RF-03", 4),),
        unjudged=(
            UnjudgedCell(
                cell=RfCell(sensor_id="RF-03", channel_index=2), reason="no baseline"
            ),
        ),
    )
    f = fault()
    bundle = build([claim_for(f)], faults=[f], rf=rf)[0]

    against = generate(bundle).evidence_against_or_uncertainty

    assert list(against) == [u.statement for u in bundle.known_uncertainties]
    assert len(against) >= 2


def test_a_not_applicable_absence_reaches_the_hypothesis_too():
    # spec: ai-002, evb-001 -- "the aircraft side was not consulted" is a
    # different statement from "the aircraft side showed nothing", and a
    # generator carrying only the measurable ones would silently promote
    # the first into the second.
    against = generate(fault_bundle()).evidence_against_or_uncertainty

    assert any("not consulted" in line for line in against)


# ------------------------------------------------------------- what it reads as


def test_the_result_is_a_valid_hypothesis_by_the_schema_not_by_construction():
    # spec: ai-002, ai-001 -- re-validating the dump catches a generator
    # that bypassed validation with model_construct, which would put an
    # unvalidated object in front of an analyst while returning the right
    # type.
    hypothesis = generate(zone_bundle())

    assert isinstance(hypothesis, Hypothesis)
    assert (
        Hypothesis.model_validate(json.loads(hypothesis.model_dump_json()))
        == hypothesis
    )


def test_composed_text_never_doubles_a_full_stop():
    # spec: ai-002 -- found on real bundles, not by a unit test: anom-005's
    # reason for a zone whose corroboration could not be measured already
    # ends in a full stop, and appending one gave "..". Cosmetic anywhere
    # else; here the output is read blind beside a language model's.
    f = fault()
    ends_in_a_stop = "one receiver deviated while its neighbours did not."
    bundle = build(
        [claim_for(f)], faults=[f], rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),))
    )[0]
    verdict = verdict_of(bundle)
    bundle = bundle.with_evidence(
        [
            replace(item, finding=ends_in_a_stop) if item is verdict else item
            for item in bundle.evidence
        ]
    )

    hypothesis = generate(bundle)

    assert ".." not in hypothesis.summary
    for citation in hypothesis.supporting_evidence:
        assert ".." not in citation.statement


def test_the_title_names_the_subject_and_the_claim():
    # spec: ai-002 -- a title reading "Anomaly detected" on every bundle is
    # schema-valid and useless, and in a blind scoring campaign it is the
    # first thing a scorer sees.
    bundle = zone_bundle()

    title = generate(bundle).hypothesis_title

    assert bundle.subject in title
    assert "interference" in title.lower()


def test_the_summary_states_the_window_the_claim_covers():
    # spec: ai-002 -- a hypothesis about an event with no time attached
    # cannot be checked against the bundle it came from.
    bundle = fault_bundle()

    summary = generate(bundle).summary

    assert bundle.time_window[0].strftime("%H:%M:%S") in summary
    assert bundle.time_window[1].strftime("%H:%M:%S") in summary


def test_the_recommended_action_differs_with_what_the_bundle_shows():
    # spec: ai-002, US-R1 -- decision support, and an action identical on a
    # broken receiver and on interference is not support. Differential,
    # because a constant string satisfies the schema's non-blank rule.
    # Both bundles are chosen to carry a track uncertainty, and each
    # action has its own subject removed before the comparison, so what is
    # left can only differ by what the generator says about this KIND of
    # claim. Without that, a single generic sentence interpolating the
    # subject passes -- which is what mutation found it doing.
    one = fault_bundle()
    other = zone_bundle(corroboration=Corroboration.NOT_MEASURABLE)

    def said_about(bundle):
        action = generate(bundle).recommended_human_action
        assert bundle.subject in action
        return action.replace(bundle.subject, "")

    assert said_about(one) != said_about(other)
    assert said_about(one).strip() and said_about(other).strip()


def test_the_recommended_action_asks_a_human_to_check_not_the_system_to_act():
    # spec: ai-002, US-R1 -- the layer is decision support and never
    # autonomous decision-making, so the action is addressed to an analyst.
    for bundle in (fault_bundle(), zone_bundle()):
        action = generate(bundle).recommended_human_action

        assert any(
            verb in action.lower()
            for verb in ("check", "verify", "confirm", "review", "corroborate")
        )
        # Addressed at this event and not at anomalies in general.
        assert bundle.subject in action


def test_the_hypothesis_carries_no_ground_truth():
    # spec: ai-002, api-009 -- the bundle carries no scenario type and the
    # hypothesis must not acquire one. A generator naming the staged
    # scenario would score perfectly and measure nothing.
    text = generate(zone_bundle()).model_dump_json().lower()

    for leak in (
        "gnss-degradation",
        "rf-sensor-fault",
        "staged",
        "answer key",
        "ground truth",
        "normal-baseline",
    ):
        assert leak not in text


def test_the_action_says_when_the_aircraft_side_is_not_a_clean_negative():
    # spec: ai-002, evb-001 -- the majority case in the corpus is a zone
    # whose discontinuity rate could not be measured at all, and an action
    # reading the same as on a corroborated zone invites an analyst to
    # treat "could not measure" as "measured and found nothing".
    corroborated = generate(zone_bundle()).recommended_human_action
    unmeasured = generate(
        zone_bundle(corroboration=Corroboration.NOT_MEASURABLE)
    ).recommended_human_action

    assert corroborated != unmeasured
    assert "aircraft" in unmeasured.lower()
    assert "aircraft" not in corroborated.lower()


# ---------------------------------------------------------------- determinism


def test_the_same_bundle_generates_the_same_hypothesis():
    # spec: ai-002, NFR-601 -- the campaign compares arms over identical
    # bundles, so a template that varied would make a difference in scores
    # unattributable to the generator.
    bundle = zone_bundle()

    assert generate(bundle) == generate(bundle)


def test_two_separately_built_identical_bundles_generate_the_same_hypothesis():
    # spec: ai-002 -- stronger than generating twice from one object,
    # which cannot catch a generator caching on identity.
    assert generate(zone_bundle()) == generate(zone_bundle())


def test_the_output_does_not_depend_on_the_hash_seed():
    # spec: ai-002, NFR-601 -- set and dict-of-string iteration order
    # varies with PYTHONHASHSEED between processes, and an unordered
    # collection in an output path is how this repository has produced a
    # result that differed between runs three times. A single-process
    # equality test cannot see it.
    script = (
        "import json\n"
        "from datetime import timedelta\n"
        "from app.ai.template import generate\n"
        "from app.detection.rf_noise import RfNoiseFindings\n"
        "from tests.test_evb_bundle import START, build, claim_for, episode, "
        "track_finding, zone\n"
        "z = zone()\n"
        "rf = RfNoiseFindings(anomalies=(episode('RF-03', 4), episode('RF-04', 4)))\n"
        "tracks = [track_finding(), "
        "track_finding('AC-aaaa1111', at=START + timedelta(seconds=30))]\n"
        "b = build([claim_for(z)], zones=[z], rf=rf, tracks=tracks)[0]\n"
        "print(generate(b).model_dump_json())\n"
    )
    root = Path(__file__).resolve().parents[1]

    def run(seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(root)}
        done = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout

    assert run("0") == run("12345")


# ------------------------------------------------- independent of everything


#: Anything that would make the correctness fallback depend on the class of
#: thing whose failure summons it. Checked across every `app` module the
#: generator can reach, not just its own import line.
FORBIDDEN = {
    "aiohttp",
    "anthropic",
    "boto3",
    "google",
    "http",
    "httpcore",
    "httpx",
    "llama_cpp",
    "ollama",
    "openai",
    "requests",
    "socket",
    "torch",
    "transformers",
    "urllib",
    "vertexai",
}


def app_import_closure(module: str) -> set[str]:
    """Every top-level module name reachable from `module` through app source."""
    root = Path(__file__).resolve().parents[1]
    seen: set[str] = set()
    reached: set[str] = set()
    queue = [module]

    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = root / Path(*name.split(".")).with_suffix(".py")
        if not path.is_file():
            path = root / Path(*name.split(".")) / "__init__.py"
        assert path.is_file(), f"cannot read {name} at {path}"

        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                targets = [node.module]
            for target in targets:
                reached.add(target.split(".")[0])
                if target.split(".")[0] == "app":
                    queue.append(target)
    return reached


def test_the_import_walker_actually_reaches_the_modules_it_claims_to():
    # spec: ai-002 -- the test below passes vacuously against a walker that
    # returns nothing, which is exactly the shape of wrong test this
    # project has now written twice.
    closure = app_import_closure("app.ai.template")

    assert "pydantic" in closure, "did not reach app.ai.hypothesis"
    assert "dataclasses" in closure, "did not reach app.detection.bundle"


def test_the_import_walker_catches_a_module_that_does_reach_the_network():
    # spec: ai-002 -- the guard below is a set intersection that is empty
    # when it works and empty when it is broken. A guard verified only
    # against the case it is meant to pass is verified against the author's
    # model of the world, which is how ops-004's first version passed ten
    # tests and did not fire. app.corpus.fetch genuinely reaches
    # urllib.request, so this is the interlock fired at a real hazard.
    assert app_import_closure("app.corpus.fetch") & FORBIDDEN == {"urllib"}


def test_the_fallback_generator_reaches_no_network_or_model_dependency():
    # spec: ai-002, ai-007 -- this is what an analyst gets when the hosted
    # provider is unreachable or the model's answer failed the grounding
    # check. A fallback that needs an HTTP client, a provider SDK or a
    # model server is not a fallback, and a comment saying so holds only
    # while everyone reads it.
    offenders = sorted(app_import_closure("app.ai.template") & FORBIDDEN)

    assert offenders == []
