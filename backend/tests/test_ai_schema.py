"""The hypothesis output schema. Spec: ai-001.

One shape, three producers. A deterministic template, a hosted model and a
local model all hand back the same seven things, which is what lets the
screen render any of them without knowing which ran and lets the evaluation
compare them at all.

The shape carries more weight than a data class usually does, for three
reasons that shape this suite:

**It is a constraint on generation, not a description of it.** The hosted
arm is given a machine-readable derivation of this model and will only emit
conforming output. So the guarantees have to survive that derivation -- a
translation that quietly widened confidence to a free string would pass
every test written against the Python model and lose the guarantee at
exactly the boundary that relies on it. Hence the derived-schema group
below, which is the half of this item that is easy to leave out.

**It is what makes `ai-008` implementable.** A supporting-evidence item is
a structured citation and never a sentence: prose cannot be resolved
against a bundle. It names `rule_id` *and* `finding_type`, because one does
not identify -- `anom-012` defines no rule id of its own and borrows
`anom-010`'s, so a rate-excess citation and a discontinuity citation are
identical by rule id while making different claims.

**Two tests here pass against a do-nothing stub, deliberately.** The
workflow calls a test that passes before the implementation a wrong test,
and four of the first draft were rewritten on exactly that grounds. Two
survive it: the positive case, which by construction passes against
anything permissive and exists to catch a schema that is too *strict* or
that drops a field, and the citation-identity test, which pins a design
decision that any implementation carrying `finding_type` satisfies. Both
fail against the plausible wrong design -- a schema missing a field, and a
citation of `rule_id` plus prose -- which is the property that matters.

**Nothing defaults.** A list that becomes empty because a generator omitted
it makes "weighed the alternatives and found none" and "never mentioned
alternatives" arrive identically. That is `evb-001`'s typed-absence
principle one layer up, and most of the refusals below are it in costume.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.hypothesis import (
    Citation,
    Confidence,
    Hypothesis,
    hypothesis_json_schema,
)

TITLE = "Probable interference affecting three receivers north of Cologne"
SUMMARY = (
    "Power on channel 4 rose 11.9 dB above baseline at RF-05, RF-06 and RF-07 "
    "within one window, and their measured neighbours did not."
)
ACTION = "Confirm against an independent spectrum source before escalating."


def citation(
    rule_id: str = "RF-NOISE", finding_type: str = "rf_noise_deviation"
) -> Citation:
    return Citation(
        rule_id=rule_id,
        finding_type=finding_type,
        statement="power rose 11.85 dB above baseline at RF-05 channel 4",
    )


def hypothesis(**overrides: object) -> Hypothesis:
    fields: dict[str, object] = {
        "hypothesis_title": TITLE,
        "confidence": Confidence.MEDIUM,
        "summary": SUMMARY,
        "supporting_evidence": (citation(),),
        "evidence_against_or_uncertainty": (
            "the aircraft side could not be measured in this window",
        ),
        "alternative_explanations": ("a fault in a single receiver",),
        "recommended_human_action": ACTION,
    }
    fields.update(overrides)
    return Hypothesis(**fields)  # type: ignore[arg-type]


# ------------------------------------------------- confidence is three words


def test_a_hypothesis_carries_one_of_exactly_three_confidences():
    # spec: ai-001, NFR-203
    assert [c.value for c in Confidence] == ["Low", "Medium", "High"]


def test_a_percentage_confidence_is_unrepresentable():
    """The item's word is *unrepresentable*, not *rejected*. A field that can
    hold only one of three words cannot hold a percentage at all."""
    # spec: ai-001, FR-715
    with pytest.raises(ValidationError):
        hypothesis(confidence="87%")


def test_a_decimal_confidence_is_unrepresentable():
    """The likelier of the two, because a model asked for a confidence
    reaches for a number. Pinned separately from the percentage, since a
    string enum that coerced would accept one and not the other."""
    # spec: ai-001, FR-715
    with pytest.raises(ValidationError):
        hypothesis(confidence=0.87)


def test_a_plausible_fourth_level_is_refused():
    """ "Very High" is what a model produces when it wants a fourth level.
    The three are ordinal and the UI renders exactly three pips."""
    # spec: ai-001, NFR-203
    with pytest.raises(ValidationError):
        hypothesis(confidence="Very High")


def test_confidence_is_case_sensitive():
    """The stored column checks against the same three spellings, so a
    lowercase value would validate here and be refused by the database."""
    # spec: ai-001, db-002
    with pytest.raises(ValidationError):
        hypothesis(confidence="medium")


# ------------------------------------------------------------ nothing defaults


@pytest.mark.parametrize(
    "field",
    [
        "hypothesis_title",
        "confidence",
        "summary",
        "supporting_evidence",
        "evidence_against_or_uncertainty",
        "alternative_explanations",
        "recommended_human_action",
    ],
)
def test_every_field_is_required(field: str):
    """Asserted per field rather than on the set, so a field that acquires a
    default is named by the failure."""
    # spec: ai-001, FR-501
    fields = {
        "hypothesis_title": TITLE,
        "confidence": Confidence.LOW,
        "summary": SUMMARY,
        "supporting_evidence": (citation(),),
        "evidence_against_or_uncertainty": (),
        "alternative_explanations": ("a receiver fault",),
        "recommended_human_action": ACTION,
    }
    del fields[field]
    with pytest.raises(ValidationError):
        Hypothesis(**fields)  # type: ignore[arg-type]


def test_omitting_the_alternatives_does_not_quietly_mean_none():
    """The item's stated failure case, and the reason nothing defaults:
    "weighed the alternatives and found none" and "never mentioned
    alternatives" must not arrive looking the same."""
    # spec: ai-001, evb-001
    with pytest.raises(ValidationError):
        hypothesis(alternative_explanations=None)


def test_an_unknown_field_is_refused_rather_than_carried():
    """A model inventing `confidence_score` would otherwise smuggle a number
    into the object whose whole point is that it holds none."""
    # spec: ai-001, FR-715
    with pytest.raises(ValidationError):
        hypothesis(confidence_score=0.87)


def test_a_hypothesis_cannot_be_edited_after_validation():
    """It is a record of what a generator produced. Something that can be
    adjusted after the grounding check ran is not that."""
    # spec: ai-001, ai-008
    built = hypothesis()
    with pytest.raises(ValidationError):
        built.confidence = Confidence.HIGH  # type: ignore[misc]


# --------------------------------------------- what a citation has to contain


def test_supporting_evidence_is_structured_and_not_prose():
    """A sentence cannot be resolved against a bundle, so a citation that is
    prose does not make `ai-008` awkward -- it makes it impossible."""
    # spec: ai-001, ai-008
    with pytest.raises(ValidationError):
        hypothesis(supporting_evidence=("the receiver was unusually noisy",))


def test_a_citation_names_both_the_rule_and_the_kind_of_finding():
    """One identifier does not identify. `anom-012` defines no rule id and
    borrows `anom-010`'s, so a rate excess and a discontinuity carry the
    same rule id while making different claims -- in every interference
    bundle the corpus produces."""
    # spec: ai-001, ai-008, anom-012
    excess = citation(rule_id="TRACK-GAP", finding_type="track_rate_excess")
    gap = citation(rule_id="TRACK-GAP", finding_type="track_continuity_gap")
    assert excess.rule_id == gap.rule_id

    # Stated as what a resolver would do with them, because that is the
    # consequence: keyed on the rule alone the two collapse into one and a
    # grounding check silently verifies the wrong claim.
    by_rule = {c.rule_id: c for c in (excess, gap)}
    by_pair = {(c.rule_id, c.finding_type): c for c in (excess, gap)}
    assert len(by_rule) == 1, "this is the ambiguity, and it is real"
    assert len(by_pair) == 2, "the pair is what identifies a citation"


@pytest.mark.parametrize("field", ["rule_id", "finding_type", "statement"])
def test_a_citation_missing_any_of_its_three_parts_is_refused(field: str):
    # spec: ai-001, FR-402
    parts = {
        "rule_id": "RF-NOISE",
        "finding_type": "rf_noise_deviation",
        "statement": "power rose 11.85 dB above baseline",
    }
    del parts[field]
    with pytest.raises(ValidationError):
        Citation(**parts)  # type: ignore[arg-type]


def test_a_hypothesis_supported_by_nothing_is_refused():
    """The thing this whole layer exists to prevent."""
    # spec: ai-001, FR-501
    with pytest.raises(ValidationError):
        hypothesis(supporting_evidence=())


def test_at_least_one_alternative_explanation_is_required():
    """Stronger than the field being present. A system built to stop a
    fluent model overclaiming must not accept "there are no alternatives",
    and the floor is satisfiable rather than decorative: a fault bundle and
    an interference bundle are each other's competing conclusion."""
    # spec: ai-001
    with pytest.raises(ValidationError):
        hypothesis(alternative_explanations=())


def test_the_uncertainty_list_may_be_explicitly_empty():
    """Deliberately not given the same floor. "Nothing speaks against this"
    can be true; "nothing else could explain this" essentially cannot.
    Whether a hypothesis carries the uncertainties its bundle carried is a
    completeness question about content, which is `ai-008`'s."""
    # spec: ai-001, ai-008
    # Asserted against its counterpart in one test, so that giving both
    # fields a floor -- or neither -- fails here. Separately, each half
    # passes against a schema that constrains nothing.
    assert (
        hypothesis(evidence_against_or_uncertainty=()).evidence_against_or_uncertainty
        == ()
    )
    with pytest.raises(ValidationError):
        hypothesis(alternative_explanations=())


@pytest.mark.parametrize(
    "field", ["hypothesis_title", "summary", "recommended_human_action"]
)
def test_an_empty_text_field_is_refused(field: str):
    """A zero-length string satisfies a `str` type and is not a title."""
    # spec: ai-001
    with pytest.raises(ValidationError):
        hypothesis(**{field: ""})


@pytest.mark.parametrize(
    "field", ["hypothesis_title", "summary", "recommended_human_action"]
)
def test_a_whitespace_text_field_is_refused(field: str):
    """The same hole one character wider, and the one a length check alone
    leaves open."""
    # spec: ai-001
    with pytest.raises(ValidationError):
        hypothesis(**{field: "   "})


def test_an_empty_citation_statement_is_refused():
    # spec: ai-001
    with pytest.raises(ValidationError):
        Citation(rule_id="RF-NOISE", finding_type="rf_noise_deviation", statement=" ")


# ------------------------------------- the rules must survive the derivation


def test_the_derived_schema_constrains_confidence_to_the_same_three():
    """**The half of this item that is easy to leave out.** The hosted arm
    is constrained by the derived schema and not by the Python model, so a
    derivation that widened confidence to a free string would pass every
    other test here and lose the guarantee at the one boundary it exists
    for."""
    # spec: ai-001, ai-004, FR-715
    schema = hypothesis_json_schema()
    confidence = schema["$defs"]["Confidence"]
    assert confidence["enum"] == ["Low", "Medium", "High"]


def test_the_derived_schema_requires_every_field():
    # spec: ai-001, ai-004
    schema = hypothesis_json_schema()
    assert set(schema["required"]) == {
        "hypothesis_title",
        "confidence",
        "summary",
        "supporting_evidence",
        "evidence_against_or_uncertainty",
        "alternative_explanations",
        "recommended_human_action",
    }


def test_the_derived_schema_carries_the_at_least_one_floors():
    """A floor that lives only in Python is a floor the hosted arm does not
    have, and the model would be free to return an empty list and be
    rejected afterwards -- which is a retry and a cost rather than a
    constraint."""
    # spec: ai-001, ai-004, ai-007
    schema = hypothesis_json_schema()
    properties = schema["properties"]
    assert properties["supporting_evidence"]["minItems"] == 1
    assert properties["alternative_explanations"]["minItems"] == 1
    assert "minItems" not in properties["evidence_against_or_uncertainty"]


def test_the_derived_schema_forbids_unknown_fields():
    """Constrained decoding is what makes the shape a guarantee. A schema
    permitting extra properties lets a model add `confidence_score` and
    still satisfy the constraint it was generating under."""
    # spec: ai-001, ai-004, FR-715
    assert hypothesis_json_schema()["additionalProperties"] is False


def test_the_derived_schema_describes_a_citation_rather_than_a_string():
    """The derivation is what tells the model to cite structurally. If this
    came out as a list of strings, the model would be *instructed* to write
    prose and `ai-008` would have nothing to resolve."""
    # spec: ai-001, ai-004, ai-008
    schema = hypothesis_json_schema()
    citation_schema = schema["$defs"]["Citation"]
    assert set(citation_schema["required"]) == {"rule_id", "finding_type", "statement"}


def test_the_derived_schema_is_stable_across_calls():
    """It is pinned into a generation request and logged beside the result
    for reproducibility, so two calls must not differ."""
    # spec: ai-001, db-002
    first, second = hypothesis_json_schema(), hypothesis_json_schema()
    assert first == second
    # Non-trivially: two empty dictionaries are also equal, and a schema
    # function returning nothing would satisfy the line above.
    assert first["$defs"]["Confidence"]["enum"] == ["Low", "Medium", "High"]


def test_a_derived_schema_caller_cannot_mutate_the_next_one():
    """A caller adjusting the schema for one request must not change what
    every later request is generated under.

    Probed at a *nested* path, not a top-level one: the first version of
    this test mutated `properties` and then read `$defs`, which are
    different subtrees, so it would have passed against a schema shared
    wholesale. Pydantic happens to return a fresh structure already, which
    makes the deep copy in the implementation redundant *at this pinned
    version* -- it is kept as defence against that changing quietly on an
    upgrade, and the mutation pass records the site as equivalent rather
    than pretending a test can distinguish it."""
    # spec: ai-001
    first = hypothesis_json_schema()
    first["$defs"]["Confidence"]["enum"] = ["anything"]
    first["properties"]["confidence"] = {"type": "string"}

    second = hypothesis_json_schema()
    assert second["$defs"]["Confidence"]["enum"] == ["Low", "Medium", "High"]
    assert second["properties"]["confidence"] != {"type": "string"}


# --------------------------------------------------------------- it is usable


def test_a_fully_specified_hypothesis_validates():
    """The positive case, asserted on values rather than on construction
    succeeding, so a field silently dropped is caught."""
    # spec: ai-001, FR-501
    built = hypothesis()
    assert built.hypothesis_title == TITLE
    assert built.confidence is Confidence.MEDIUM
    assert built.summary == SUMMARY
    assert built.recommended_human_action == ACTION
    assert built.alternative_explanations == ("a fault in a single receiver",)
    assert built.evidence_against_or_uncertainty == (
        "the aircraft side could not be measured in this window",
    )
    # The lists are tuples and the citation is a Citation, both asserted
    # rather than assumed: a generator hands over parsed JSON, so a model
    # that left `supporting_evidence` as a list of dictionaries would carry
    # dictionaries everywhere downstream and fail at the grounding check
    # rather than here.
    assert isinstance(built.supporting_evidence, tuple)
    assert isinstance(built.supporting_evidence[0], Citation)
    assert built.supporting_evidence[0].rule_id == "RF-NOISE"


def test_a_citation_given_as_plain_json_becomes_a_citation():
    """What a model actually returns is parsed JSON, so this is the shape
    the hosted arm exercises and the one above is not."""
    # spec: ai-001, ai-004
    built = hypothesis(
        supporting_evidence=[
            {
                "rule_id": "SENSOR-FAULT",
                "finding_type": "neighbour_nominal",
                "statement": "RF-02 stayed within 2.0 dB of its baseline",
            }
        ]
    )
    assert isinstance(built.supporting_evidence[0], Citation)
    assert built.supporting_evidence[0].finding_type == "neighbour_nominal"
