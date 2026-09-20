"""The template hypothesis generator. Spec: ai-002.

The first producer of an explanation in this system, and the one with no
model in it. It reads an evidence bundle and writes the hypothesis out by
rule -- the same bundle always yields the same words.

It has two jobs, and the design follows from having both at once.

**The correctness fallback.** When a model arm returns something that fails
validation or fails `ai-008`'s grounding check, this is what the analyst
gets instead of an error (`ai-007`). A fallback that shares a dependency
with the thing whose failure summons it is not a fallback, so the
independence is asserted from the import graph rather than promised here:
the suite walks every `app` module reachable from this one and refuses an
HTTP client, a provider SDK or a model server anywhere in the closure.

**The evaluation baseline.** The research question is whether a language
model adds anything over an honest mechanical summary of the same
evidence, and that has no answer without the honest mechanical summary.
The campaign scores this blind alongside the model arms, so it must be
good enough to hand an analyst and plain enough that it cannot flatter
itself.

Everything it emits is taken from the bundle, so a template hypothesis is
**grounded by construction** -- which inverts what running `ai-008` over
one means: anything the grounding check flags here is a defect in the
check, not in the generator.

Three decisions are worth reading before the code.

**Confidence is inherited, never computed.** Every bundle carries the
deciding rule's own confidence on its verdict item, and that value was
measured and argued when the rule was built -- `anom-007`'s qualifies an
attribution, `anom-005`'s has a floor of Medium the track side cannot
breach. A second scoring scheme here would be a constant repeated in two
modules, which is a constant that will eventually disagree with itself
while both halves keep working. The two vocabularies do not match, either:
the detection layer spells it `low` and `ai-001`'s schema demands `Low`.
The join is **by enum member name**, so an unrecognised word raises here
rather than being laundered by `.title()` into something that looks valid
and only fails at the schema, one layer too late to say which bundle.

**A citation stands for a kind of evidence, not for an item.** A real
bundle carries 34 items of four kinds; one citation per item is complete
and unreadable, one per kind is both. The grouping key is exactly the
`(rule_id, finding_type)` pair `ai-001` defines as a citation's identity,
and this is the first consumer where that choice is visible: `anom-012`
borrows `anom-010`'s rule id, so grouping on the rule alone would collapse
a rate excess and a discontinuity into one citation making neither claim.
`rule_id` and `finding_type` are copied verbatim; only `statement` is
composed, and `statement` is not what `ai-008` resolves.

**Alternatives come from what the system already ruled out.** A claim
`anom-013` suppressed *is* a competing conclusion, recorded as one -- so
those are the alternatives, and a generator inventing alternatives while
ignoring them would be disagreeing with its own evidence. A suppressed
claim reaching `supporting_evidence` would undo the one thing `evb-001`
refuses to make possible, so it never does. Below that sits the standing
pair: a broken receiver and interference in the environment are each
other's competing conclusion. Last, and unconditionally, sits the caveat
that the deterministic rules can only choose among the conclusions they
encode -- true of every bundle, omitted by every fluent generator, and it
is what keeps `ai-001`'s floor of one satisfied by construction for a
bundle type that does not exist yet. A fallback generator that raised on
an unfamiliar anomaly type would fail at exactly the moment it is needed.

Known uncertainties are copied **verbatim and untruncated**, in bundle
order. They are already written out in prose that carries which kind of
not-knowing each one is (`evb-001` requires that), so copying composes
nothing; and dropping a tail to keep the text short loses the distinction
between measured-and-negative and never-looked, which is the material this
whole layer exists to preserve.

Recorded as a threat to validity rather than solved: the template's
confidence is inherited and therefore cannot be miscalibrated in the way a
model's can, so that scoring dimension compares two different mechanisms
rather than two answers to one question. See `docs/thesis_notes.md`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from app.ai.hypothesis import Citation, Confidence, Hypothesis
from app.ai.service import GenerationError
from app.detection.bundle import EvidenceBundle, EvidenceItem
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE
from app.detection.sensor_fault import ANOMALY_TYPE as SENSOR_FAULT


class TemplateError(GenerationError):
    """A bundle this generator will not turn into a hypothesis.

    A `GenerationError`, and deliberately **neither** of its two
    categories. `ai-006` falls back on a provider being unavailable and
    `ai-007` falls back on a model's output being unusable; this is the
    thing both of them fall back *to*. A refusal here means the bundle
    itself cannot be explained, and a handler that responded by reaching
    for the template would have nowhere to go (`ai-003`).

    Every case is a bundle that would force an invention: a missing
    verdict, an ambiguous one, or a confidence that is absent or is not a
    word this system recognises. Refusing is the whole point -- a default
    here is a claim about the evidence that nothing measured.
    """


#: What each kind of claim's counterpart is, when the ladder recorded no
#: suppression to name one. Each entry is the other's, deliberately: a
#: single receiver deviating and a region of receivers deviating together
#: are the two readings of the same radio evidence, and `anom-007` exists
#: precisely to separate them.
_STANDING_ALTERNATIVE = {
    SENSOR_FAULT: (
        f"{INTERFERENCE}: the deviation may be a real signal in the "
        "environment rather than a fault in the receiver. The rule ruled "
        "this out because the measured neighbouring receivers stayed "
        "nominal through the same window, so a neighbour that could not be "
        "measured weakens that argument."
    ),
    INTERFERENCE: (
        f"{SENSOR_FAULT}: the deviation may be in the receivers rather than "
        "in the environment. The rule ruled this out because more than one "
        "receiver deviated together, so a common-mode failure -- a shared "
        "power supply, a shared clock, one configuration change applied to "
        "several units -- is the reading this does not exclude."
    ),
}

#: Appended to every hypothesis, last. True of every bundle this system
#: can produce, and the caveat a fluent generator omits.
_OUTSIDE_THE_RULES = (
    "something the rule set does not encode: these conclusions are drawn by "
    "deterministic rules that can only choose among the explanations they "
    "were written to distinguish, so an event unlike any of them is "
    "reported as whichever encoded explanation it most resembles."
)

#: What to ask a human to do, per kind of claim. Decision support, so every
#: one of these is addressed to an analyst and none of them is an action
#: the system takes.
_ACTION = {
    SENSOR_FAULT: (
        "Check the receiver at {subject} against its own maintenance record "
        "and its neighbours' readings for the same window before treating "
        "the deviation as a signal in the environment."
    ),
    INTERFERENCE: (
        "Corroborate the deviation at {subject} against a source outside "
        "this system -- a NOTAM, a spectrum-monitoring report, an operator "
        "log -- before treating it as interference in the environment."
    ),
}

_GENERIC_ACTION = (
    "Review the cited observations for {subject} against the window they "
    "cover before acting on this account."
)


def generate(bundle: EvidenceBundle) -> Hypothesis:
    """One hypothesis from one bundle, deterministically and with no model."""
    verdict = _verdict(bundle)
    return Hypothesis(
        hypothesis_title=_title(bundle),
        confidence=_confidence(bundle, verdict),
        summary=_summary(bundle, verdict),
        supporting_evidence=_citations(bundle),
        evidence_against_or_uncertainty=tuple(
            u.statement for u in bundle.known_uncertainties
        ),
        alternative_explanations=_alternatives(bundle),
        recommended_human_action=_action(bundle),
    )


# ---------------------------------------------------------------- the verdict


def _verdict(bundle: EvidenceBundle) -> EvidenceItem:
    """The item carrying the bundle's own conclusion. Exactly one.

    `evb-002`'s rule about citations, applied one layer up: a lookup is a
    resolution only if it returns exactly one row. Zero means the
    confidence and the lead sentence would both have to be invented; more
    than one means taking whichever came first, which is the unordered
    result this repository has now recorded three times.
    """
    found = [
        item for item in bundle.evidence if item.finding_type == bundle.anomaly_type
    ]
    if not found:
        raise TemplateError(
            f"the bundle claims {bundle.anomaly_type!r} on {bundle.subject!r} "
            "and carries no evidence item stating that conclusion. The "
            "hypothesis takes its confidence and its lead sentence from that "
            "item, so without one both would have to be invented."
        )
    if len(found) > 1:
        raise TemplateError(
            f"the bundle carries {len(found)} items stating "
            f"{bundle.anomaly_type!r} on {bundle.subject!r}. Taking the first "
            "would make the hypothesis depend on the order the builder "
            "happened to emit them in."
        )
    return found[0]


def _confidence(bundle: EvidenceBundle, verdict: EvidenceItem) -> Confidence:
    """The deciding rule's own confidence, joined by enum member name."""
    word = verdict.details.get("confidence")
    if not isinstance(word, str):
        raise TemplateError(
            f"the {bundle.anomaly_type!r} verdict on {bundle.subject!r} "
            f"carries confidence {word!r}. This generator reads the rule's "
            "own confidence rather than computing a second one, so there is "
            "nothing to fall back to -- and a default would be a claim about "
            "the evidence that nothing measured."
        )
    try:
        return Confidence[word.upper()]
    except KeyError:
        raise TemplateError(
            f"the {bundle.anomaly_type!r} verdict on {bundle.subject!r} "
            f"reports confidence {word!r}, which is not one of "
            f"{', '.join(c.name.lower() for c in Confidence)}. The join is by "
            "name so an unfamiliar word is refused here rather than "
            "capitalised into something that merely looks valid."
        ) from None


# -------------------------------------------------------------- the citations


def _citations(bundle: EvidenceBundle) -> tuple[Citation, ...]:
    """One citation per kind of evidence, in first-appearance order.

    Grouped on the `(rule_id, finding_type)` pair rather than the rule
    alone -- see the module docstring on why the rule alone does not
    identify. A plain dict is the grouping, because its insertion order is
    the bundle's order and nothing here may depend on a set.
    """
    grouped: dict[tuple[str, str], list[EvidenceItem]] = {}
    for item in bundle.evidence:
        grouped.setdefault((item.rule_id, item.finding_type), []).append(item)

    return tuple(
        Citation(
            rule_id=rule_id, finding_type=finding_type, statement=_statement(items)
        )
        for (rule_id, finding_type), items in grouped.items()
    )


def _statement(items: Sequence[EvidenceItem]) -> str:
    """What this kind of evidence says, in the generator's own words.

    A group of one is quoted rather than described: nothing is composed,
    which is the most grounded a citation can be. A group of several names
    how many it stands for, because a citation reading like one finding
    while standing for six understates the evidence -- and for a baseline,
    understating is the direction that matters.
    """
    first = items[0]
    if len(items) == 1:
        return f"{first.source}: {_sentence(first.finding)}"

    sources: list[str] = []
    for item in items:
        if item.source not in sources:
            sources.append(item.source)
    started = min(item.started_at for item in items)
    ended = max(item.ended_at for item in items)
    return (
        f"{len(items)} findings of this kind across "
        f"{len(sources)} source(s) between {_clock(started)} and "
        f"{_clock(ended)}; for example, {first.source}: "
        f"{_sentence(first.finding)}"
    )


def _sentence(text: str) -> str:
    """One full stop, whatever the source text arrived with.

    Found on real bundles and not by any unit test: `anom-005`'s reason
    for a zone whose corroboration could not be measured is three
    sentences and ends in a full stop, so appending one produced "..".
    Cosmetic everywhere else and not here -- this generator's output is
    read blind beside a language model's, where punctuation a model would
    never produce reads as a quality difference.
    """
    return text.rstrip(". ") + "."


def _clock(when: datetime) -> str:
    """Time of day, UTC. The date is stated once, in the summary."""
    return when.strftime("%H:%M:%S")


# ------------------------------------------------------------ the prose fields


def _readable(anomaly_type: str) -> str:
    return anomaly_type.replace("_", " ")


def _title(bundle: EvidenceBundle) -> str:
    """Names the claim and where it is.

    A title reading "Anomaly detected" is schema-valid and useless, and in
    a blind scoring campaign it is the first thing a scorer sees.
    """
    claim = _readable(bundle.anomaly_type)
    return f"{claim[:1].upper()}{claim[1:]} at {bundle.subject}"


def _summary(bundle: EvidenceBundle, verdict: EvidenceItem) -> str:
    """The claim, its window, the rule's own words, and what is behind it."""
    started, ended = bundle.time_window
    kinds = len({(item.rule_id, item.finding_type) for item in bundle.evidence})
    channels = (
        f", on channel(s) {', '.join(str(c) for c in bundle.affected_channels)}"
        if bundle.affected_channels
        else ""
    )
    return (
        f"{verdict.rule_id} reports {_readable(bundle.anomaly_type)} at "
        f"{bundle.subject} between {started.strftime('%Y-%m-%d %H:%M:%S')} and "
        f"{_clock(ended)} UTC{channels}. The rule states: "
        f"{_sentence(verdict.finding)} Behind it are {len(bundle.evidence)} evidence "
        f"item(s) of {kinds} kind(s), with "
        f"{len(bundle.known_uncertainties)} recorded uncertainty(ies). This "
        "account restates what the detection rules found and adds nothing "
        "to it."
    )


def _alternatives(bundle: EvidenceBundle) -> tuple[str, ...]:
    """What else this evidence could be, starting with what was ruled out."""
    out = [
        f"{claim.anomaly_type}: claimed here by {claim.rule_id} and set aside "
        f"in favour of {claim.claimed_by}, because {claim.reason}. It is a "
        "competing account of the same evidence, not a second finding "
        "supporting this one."
        for claim in bundle.superseded
    ]
    standing = _STANDING_ALTERNATIVE.get(bundle.anomaly_type)
    if standing is not None:
        out.append(standing)
    out.append(_OUTSIDE_THE_RULES)
    return tuple(out)


def _action(bundle: EvidenceBundle) -> str:
    """What to ask an analyst to do. Never what the system will do."""
    template = _ACTION.get(bundle.anomaly_type, _GENERIC_ACTION)
    action = template.format(subject=bundle.subject)
    if any(u.subject == "track" for u in bundle.known_uncertainties):
        action += (
            " The aircraft side is not a clean negative here -- see the "
            "uncertainties -- so it should not be read as evidence against."
        )
    return action


__all__ = ["TemplateError", "generate"]
