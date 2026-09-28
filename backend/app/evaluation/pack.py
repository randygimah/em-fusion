"""The scoring pack a marker receives. Spec: eval-004.

The **second** of that item's two passes. The first drew the twenty packages
and was committed before anything was asked; this renders what a marker
reads, after `ai-012` has run.

**Three of the four things that matter here are about what must not be
inferable.** `docs/scoring_rubric.md` already concedes the blinding is
imperfect: template prose is stylistically distinctive and a marker may
recognise it, and that residual threat is stated in the Evaluation chapter
rather than claimed away. What must not be *added* to it is a **formatting**
leak. Style is a hint a marker sometimes acts on; a stray blank line or a
different field order is a perfect classifier. So one renderer serves both
arms, the A/B labels are reshuffled per package, and the arm key is written
somewhere the marker never looks.

**The scored generation is taken by its ordinal**, not by row order. It is
generation 1, fixed in advance, and it is **not substituted when it fell
back**: a first generation the model failed and `ai-002` answered is what the
hosted arm *delivered* on that bundle, and substituting the second would
delete every failure from the scored corpus and flatter the arm under test --
an omission that would be invisible in the results.

**Everything is refused rather than left blank.** A missing hypothesis
renders as an empty section, and the rubric tells a marker that a missing
section scores 1 -- so a silently absent item would score its arm at the
floor. An unpaired bundle contributes a score to one arm with nothing to
subtract it from, which is worse than one bundle fewer.

Nothing here reaches a database or a model. The bundles and hypotheses arrive
as the caller has already read them, following `eval-005`.
"""

from __future__ import annotations

import csv
import io
import os
import random
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.ai.campaign import GenerationRecord
from app.ai.hypothesis import Hypothesis
from app.ai.service import ConfigurationError, GeneratorKind
from app.detection.bundle import EvidenceBundle

#: The five ordinal dimensions of pass one, then the two categorical
#: judgements of pass two, spelled as `docs/scoring_rubric.md` spells them.
#: The count is load-bearing: 40 items x 5 is the 280 values quoted in the
#: participant information sheet and on the ethics approval form, and those
#: three places change together or the consent is no longer informed by the
#: right number.
DIMENSIONS: tuple[str, ...] = (
    "evidence_use",
    "uncertainty",
    "alternatives",
    "actionability",
    "overall_usefulness",
)

#: Pass two, made after the marker is told what was really happening.
JUDGEMENTS: tuple[str, ...] = ("cause_correctness", "confidence_calibration")

#: The generation `eval-004` scores. Declared rather than passed in: a
#: caller able to choose it could choose it after reading one.
SCORED_ORDINAL = 1

LABELS = ("A", "B")

#: Words that would name an arm in the marker's own files, and **not** simply
#: the arm vocabulary. `GeneratorKind` has three values and only two of them
#: are safe to search for.
#:
#: `local` is excluded because it is ordinary English in this domain, and the
#: first real pack proved it: *"the local discontinuity rate could not be
#: measured"* is `anom-012`'s own language in the baseline, and *"caused by
#: local equipment malfunction"* came from the model. A check that fires on
#: honest prose is not a weaker check, it is a broken one -- it would have to
#: be switched off, and then it guards nothing.
#:
#: `model` and `baseline` are excluded on the same argument: an explanation
#: may honestly say *"a propagation model"*. The first version of the test
#: forbade them and failed on its own fixture; this version forbade `local`
#: and passed on fixtures that never used the word, then fired on the first
#: real pack. Both are the same mistake, and the second one is the reason
#: this list is a named constant rather than a literal in two places.
#:
#: **The real guarantee is structural, and this is a canary.** The renderer
#: reads only the hypothesis's own fields; the arm lives on `PackItem` and is
#: written to the key alone. If that ever stops being true, these two words
#: are what would show it.
BLINDING_GIVEAWAYS: tuple[str, ...] = ("hosted", "template")


#: Words that turn a definition into an interpretation. A glossary entry
#: says what a term **denotes** and never what it **implies**.
#:
#: *"one aircraft's position reports stopping"* is a definition. *"...which
#: indicates interference in the area"* is the answer to the question the
#: marker is being paid to answer -- evidence use asks whether an
#: explanation reasons from the findings, and cause correctness asks in pass
#: two whether it identified what was happening. A glossary that supplies
#: either has moved part of the instrument into the reference material,
#: where nobody would look for it.
#:
#: This is `eval-007`'s summarising-pack failure in its most dangerous form,
#: because prose reasoning does not look like a computation and so does not
#: trip the "computes no new number" guard. Hence a list of its own, on
#: `BLINDING_GIVEAWAYS`' pattern: the constant is the argument, it lives in
#: one place, and every entry is checked against it.
CAUSAL_CONNECTIVES: tuple[str, ...] = (
    "because",
    "caused by",
    "due to",
    "evidence of",
    "implies",
    "implying",
    "indicates",
    "indicating",
    "likely",
    "means that",
    "points to",
    "suggests",
    "suggesting",
    "therefore",
    "which shows",
)

#: Every term a marker meets in these packs, defined denotatively.
#:
#: Keyed by exactly the string that appears in the pack -- a citation key is
#: matched character for character by a marker checking a citation, so a
#: glossary spelling it differently is a glossary they cannot use.
#:
#: Only the entries whose terms actually appear in an exported pack are
#: rendered, and a citation key with no entry here is refused rather than
#: omitted: a silently missing definition is how a marker meets an undefined
#: rule mid-flow, with nothing about the page looking wrong.
GLOSSARY: dict[str, str] = {
    # --- the rules that produce findings
    "RF-NOISE": (
        "The rule that compares each radio reading against what that receiver "
        "normally reads on that channel."
    ),
    "TRACK-GAP": (
        "The rule that looks for aircraft whose position reports stop arriving."
    ),
    "SENSOR-FAULT": (
        "The rule that compares one receiver against the receivers near it."
    ),
    "FUSION-SPATIAL": (
        "The rule that reports when more than one receiver deviated in the same "
        "area and the same window."
    ),
    # --- the conclusions a pack is about
    "possible_interference_zone": (
        "The conclusion that more than one receiver deviated at the same time in "
        "the same area."
    ),
    "possible_sensor_fault": (
        "The conclusion that one receiver deviated while the neighbours that "
        "could be measured stayed within their normal range."
    ),
    # --- the findings themselves
    "rf_noise_deviation": (
        "One run of consecutive readings on one receiver and one channel that "
        "sat far enough from that cell's normal to be recorded as an event."
    ),
    "track_continuity_gap": (
        "One aircraft's position reports stopping for longer than the gap the "
        "rule allows."
    ),
    "track_rate_excess": (
        "How often aircraft dropped out inside the window, set against how often "
        "they dropped out in the same area outside it."
    ),
    "neighbour_nominal": (
        "A receiver near the one under examination that was measured and stayed "
        "within its normal range."
    ),
    "channel_adjacency": (
        "How many of a receiver's channels the deviation covered, out of the "
        "total it watches."
    ),
    # --- words in the findings' own prose
    "baseline": (
        "The average and spread of what one receiver reads on one channel, "
        "worked out from quiet periods only. Every receiver and channel has its "
        "own; they are never pooled."
    ),
    "channel": (
        "One slice of the radio spectrum. Each receiver watches several, "
        "numbered from 0."
    ),
    "dB": (
        "Decibel, the unit these readings use. It is a ratio on a logarithmic "
        "scale: 3 dB is about double, 10 dB is ten times, 20 dB is a hundred "
        "times."
    ),
    "power_dbm": "Received signal power, in decibels relative to one milliwatt.",
    "nominal": "Within the normal range for that receiver and channel.",
    "disc": (
        "A circular area of the stated radius, centred on the event, used to "
        "decide which aircraft count as near it."
    ),
    "discontinuity": "One break in one aircraft's stream of position reports.",
    "reference period": (
        "The time outside the event window, used as the comparison for a rate."
    ),
    "rate ratio": (
        "The rate inside the window divided by the rate in the reference period."
    ),
    "smoothing constant": (
        "A small fixed number added to both sides of a rate comparison so that a "
        "division by zero cannot occur."
    ),
    "corroborate": (
        "To look for agreement from the other half of the picture -- the "
        "aircraft side for a radio finding, and the reverse. Recorded as one of "
        "three values: corroborated, measured and not corroborated, or not "
        "measurable."
    ),
}


@dataclass(frozen=True, slots=True)
class PackItem:
    """One hypothesis as the marker meets it, and what it really was."""

    item_id: str
    bundle_id: int
    label: str
    #: Held here and written only to the key. Nothing that renders the
    #: marker's files may read it.
    arm: GeneratorKind
    hypothesis: Hypothesis


@dataclass(frozen=True, slots=True)
class ScoringPack:
    """Three files: two for the marker, one held back."""

    hypotheses_md: str
    score_sheet_csv: str
    arm_key_csv: str
    items: tuple[PackItem, ...]
    bundles: int
    items_per_bundle: int

    @property
    def values_per_rater(self) -> int:
        """Pass-one values one marker is being asked for.

        Reported so the figure on the consent form can be checked against
        what was actually exported rather than against what was planned.
        """
        return len(self.items) * len(DIMENSIONS)


def build_pack(
    *,
    generations: Sequence[GenerationRecord],
    bundles: Sequence[tuple[int, EvidenceBundle]],
    hypotheses: Mapping[int, Hypothesis],
    seed: int,
) -> ScoringPack:
    """Render the pack, the blank sheet, and the key held separately.

    Takes the **generations** rather than a whole `CampaignRecord`, because
    that is all it uses: a campaign's budget and grounding ledger are
    `eval-005`'s and have no bearing on what a marker reads. It also means a
    caller reading a stored record off disk hands over what it loaded rather
    than assembling a record around it with two empty fields -- which is the
    hand-written-object hazard `ai-004`'s payload module exists because of.
    """
    held = dict(bundles)
    scored = _scored_generations(generations)

    items: list[PackItem] = []
    sections: list[str] = []
    ordered = sorted(scored)
    for position, bundle_id in enumerate(ordered, start=1):
        arms = scored[bundle_id]
        if len(arms) < 2:
            raise ConfigurationError(
                f"bundle {bundle_id} has only one arm in the campaign record. "
                "The design is paired within bundle, so an unpaired item "
                "contributes a score to one arm with nothing to subtract it "
                "from -- which is worse than one bundle fewer."
            )
        if bundle_id not in held:
            raise ConfigurationError(
                f"bundle {bundle_id} was generated for but no evidence bundle "
                "was supplied. A hypothesis exported without the evidence it "
                "explains gives the marker nothing to judge it against, and "
                "evidence use is the first dimension."
            )

        # One draw per bundle, so A on one page has nothing to do with A on
        # the next -- the rubric's own words, and what stops a marker who
        # worked out one package working out all twenty.
        order = sorted(arms, key=lambda arm: arm.value)
        # Keyed per bundle from one number, so the whole pack is
        # reproducible from the seed and no bundle's draw depends on the one
        # before it. A string key rather than a tuple: a tuple seed is not
        # accepted, and arithmetic on the two would collide for some pairs.
        random.Random(f"{seed}:{bundle_id}").shuffle(order)

        paired: list[PackItem] = []
        for label, arm in zip(LABELS, order):
            row = arms[arm]
            if row not in hypotheses:
                raise ConfigurationError(
                    f"no hypothesis was supplied for row {row} on bundle "
                    f"{bundle_id}. Rendered blank it becomes a missing "
                    "section, which the rubric tells a marker to score 1 -- "
                    "so an absent item would score its arm at the floor."
                )
            paired.append(
                PackItem(
                    item_id=f"{bundle_id:05d}-{label}",
                    bundle_id=bundle_id,
                    label=label,
                    arm=arm,
                    hypothesis=hypotheses[row],
                )
            )
        items.extend(paired)
        sections.append(
            _section(
                bundle_id,
                held[bundle_id],
                paired,
                position=position,
                total=len(ordered),
            )
        )

    return ScoringPack(
        hypotheses_md=(
            _preamble(len(scored))
            + _glossary(
                [(b, held[b]) for b in ordered if b in held], "\n".join(sections)
            )
            + "\n---\n\n".join(sections)
        ),
        score_sheet_csv=_sheet(items),
        arm_key_csv=_key(items),
        items=tuple(items),
        bundles=len(scored),
        items_per_bundle=len(LABELS),
    )


def _scored_generations(
    generations: Sequence[GenerationRecord],
) -> dict[int, dict[GeneratorKind, int]]:
    """Each bundle's scored row per arm, taken by **ordinal**.

    By ordinal and never by position, which would silently export a
    different generation on any bundle whose rows were written in another
    order -- and on a bundle where generation 1 fell back, that is exactly
    the substitution the pre-registration forbids.
    """
    found: dict[int, dict[GeneratorKind, int]] = {}
    for generation in generations:
        if generation.ordinal != SCORED_ORDINAL:
            continue
        found.setdefault(generation.bundle_id, {})[
            generation.requested_arm
        ] = generation.hypothesis_id
    return found


# --------------------------------------------------------------- rendering
#
# One renderer, used for both arms. Anything below that branched on the arm
# would be a formatting leak, which is a *perfect* classifier where the prose
# style the rubric already concedes is only a hint.


def _glossary(bundles: Sequence[tuple[int, EvidenceBundle]], prose: str) -> str:
    """The terms this pack actually uses, defined.

    Filtered to what is present, because a definition for something the
    marker will never meet is one more line to read past and twenty of them
    is a page of them. A citation key with no entry is **refused**: omitted,
    the page still looks complete and the marker meets an undefined rule
    nineteen packs from the end.
    """
    keys: list[str] = []
    for bundle_id, bundle in bundles:
        for item in bundle.evidence:
            for key in (item.rule_id, item.finding_type):
                if key and key not in keys:
                    keys.append(key)
                    if key not in GLOSSARY:
                        raise ConfigurationError(
                            f"bundle {bundle_id} cites {key!r}, which has no "
                            "glossary entry. Left out, the pack still reads as "
                            "complete and the marker meets an undefined term "
                            "mid-flow with nothing looking wrong -- so a rule "
                            "added later is defined here or it is not exported."
                        )

    # Matched against **everything the marker reads**, the rendered
    # explanations included -- `corroborate` appears only there, and a scan
    # over the findings alone leaves out one of the words most likely to
    # stop somebody mid-pack. Pooled across all twenty packs and both
    # labels, so what the glossary holds says nothing about any one pack.
    lowered = prose.lower()
    for term in GLOSSARY:
        if term not in keys and term.lower() in lowered:
            keys.append(term)

    lines = [
        "## Terms used in these packs",
        "",
        "Definitions, not interpretations: each entry says what the word refers "
        "to, and deliberately not what it would mean if you saw it. Judging "
        "that is the job.",
        "",
        "| Term | What it refers to |",
        "|---|---|",
    ]
    lines += [
        f"| `{_cell(term)}` | {_cell(GLOSSARY[term])} |"
        for term in sorted(keys, key=_glossary_order)
    ]
    return "\n".join(lines) + "\n\n---\n\n"


def _glossary_order(term: str) -> tuple[int, str]:
    """Rules first, then conclusions, then findings, then plain words.

    A marker looking a term up has the citation key in front of them, so the
    keys are grouped together rather than interleaved alphabetically with
    ordinary words like *baseline*.
    """
    if term.isupper() or "-" in term and term.replace("-", "").isupper():
        return (0, term)
    if term.startswith("possible_"):
        return (1, term)
    if "_" in term:
        return (2, term)
    return (3, term)


def _preamble(bundles: int) -> str:
    return (
        "# Hypothesis scoring pack\n\n"
        f"{bundles} evidence packs. Under each one are two short "
        "explanations, labelled A and B. They were produced by two different "
        "systems. You are not told which is which, and **the labels are "
        "reshuffled on every pack** -- A here has nothing to do with A on the "
        "next one.\n\n"
        "Each pack is laid out the same way: what the detection rules "
        "concluded, the findings behind that conclusion, and what the rules "
        "could not determine. Read the pack first, then both explanations, "
        "then score each one **on its own terms** in the scoring workbook.\n\n"
        "Findings are grouped by the rule that produced them, and every "
        "finding is still listed individually under its group. The grouping "
        "is there to save you re-reading near-identical lines; it is not a "
        "summary, and nothing has been left out.\n\n"
        "Two explanations under one pack may occasionally be identical or "
        "nearly so. That is expected rather than a fault in the pack.\n\n"
        "---\n\n"
    )


def _cell(text: str) -> str:
    """One value, safe to put in a Markdown table cell.

    A pipe inside a finding would end the cell early and silently drop the
    rest of the sentence -- which on an evidence pack is the marker reading
    a truncated claim and scoring it.
    """
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _conclusion(bundle_id: int, bundle: EvidenceBundle) -> Any:
    """The evidence item carrying the bundle's own conclusion.

    Found by `finding_type == anomaly_type` and required to exist **exactly
    once**, which is `ai-002`'s rule and `evb-002`'s exactly-one-row rule a
    layer up. Rendered with an arbitrary lead instead, the marker reads
    whichever item happened to come first as the claim under scrutiny.
    """
    found = [
        item for item in bundle.evidence if item.finding_type == bundle.anomaly_type
    ]
    if len(found) != 1:
        raise ConfigurationError(
            f"bundle {bundle_id} carries {len(found)} evidence item(s) whose "
            f"finding type is its own anomaly type {bundle.anomaly_type!r}, and "
            "the pack leads with that conclusion. Exactly one is required: with "
            "none there is nothing to lead with, and with several the marker "
            "would read whichever came first as the conclusion under scrutiny."
        )
    return found[0]


def _section(
    bundle_id: int,
    bundle: EvidenceBundle,
    items: Sequence[PackItem],
    *,
    position: int,
    total: int,
) -> str:
    """One pack, written to be read rather than merely to be correct.

    Two rounds were needed and the first one's lesson is worth keeping. The
    original emitted space-aligned plain text, which every renderer reflowed
    into one paragraph. Fixing that produced valid Markdown that was still a
    wall: fourteen table rows repeating *power_dbm deviated by X dB at its
    peak* and fifteen repeating *reporting from this aircraft broke during
    the window* carry one sentence and N values between them, and it is the
    sentence the eye has to re-read. So the shared text is **factored** --
    said once in the group's heading, with each row keeping only what
    differs. Nothing is removed; the repetition is.
    """
    conclusion = _conclusion(bundle_id, bundle)
    start, end = bundle.time_window
    channels = ", ".join(str(c) for c in bundle.affected_channels)
    lines = [
        f"## Evidence pack {bundle_id:05d} -- {position} of {total}",
        "",
        "| | |",
        "|---|---|",
        f"| **When** | {start:%Y-%m-%d %H:%M} to {end:%H:%M} |",
        f"| **Where** | {_cell(bundle.subject)}"
        + (f" &middot; channel {_cell(channels)}" if channels else "")
        + " |",
        "",
        "### The conclusion being explained",
        "",
        # Not bolded: a rule's conclusion can run to three lines, and three
        # bold lines is a heavier signal than the blockquote already gives.
        f"> {_cell(conclusion.finding)}",
        ">",
        f"> *{conclusion.rule_id} / {conclusion.finding_type}*"
        + (f" &middot; {_cell(conclusion.source)}" if conclusion.source else ""),
        "",
    ]

    rest = [item for item in bundle.evidence if item is not conclusion]
    if rest:
        lines += ["### The evidence behind it", ""]
        for (rule_id, finding_type), group in _grouped(rest).items():
            lines += _group_block(rule_id, finding_type, group)

    if bundle.known_uncertainties:
        lines += ["### What the rules could not determine", ""]
        lines += _uncertainty_block(bundle.known_uncertainties)

    for item in items:
        lines.append(_rendered(item))
    # The rule between packs is joined *between* sections and never appended
    # here. Appended, it lands after the last hypothesis only -- which makes
    # B's block end in something A's does not, and a formatting difference
    # between the two labels is a perfect classifier.
    return "\n".join(lines)


def _group_block(rule_id: str, finding_type: str, group: Sequence[Any]) -> list[str]:
    """One kind of finding, with the sentence they share said once.

    The rule and finding type **lead** the block, because that pair is
    exactly how a hypothesis cites its evidence (`ai-001`) and checking a
    citation against the pack is the first of the five scored dimensions.
    Every block has the same three parts whatever its size, so a marker
    learns the shape once -- and so nothing about the layout can vary with
    what a block happens to contain.
    """
    noun = "finding" if len(group) == 1 else "findings"
    lines = [f"**{rule_id} / {finding_type}** &middot; {len(group)} {noun}", ""]

    shared, differing = _factored([finding.finding for finding in group])

    if len(group) == 1:
        finding = group[0]
        source = f"**{_cell(finding.source)}** -- " if finding.source else ""
        return lines + [f"{source}{_cell(finding.finding)}", ""]

    # Gathered under the source rather than one row per finding: the source
    # is a field on the item, so this reorders what is already there and
    # computes nothing.
    by_source: dict[str, list[str]] = {}
    for finding, value in zip(group, differing):
        by_source.setdefault(finding.source or "--", []).append(value)

    if shared:
        lines += [_cell(shared), ""]

    if not any(value for value in differing):
        # Identical wording: there is nothing left to put in a second
        # column, and the sources alone are the group.
        lines += [
            " &middot; ".join(
                source if len(values) == 1 else f"{source} (x{len(values)})"
                for source, values in by_source.items()
            ),
            "",
        ]
        return lines

    lines += ["| Source | |", "|---|---|"]
    lines += [
        f"| {_cell(source)} | {' &middot; '.join(_cell(v) for v in values)} |"
        for source, values in by_source.items()
    ]
    lines.append("")
    return lines


def _uncertainty_block(uncertainties: Sequence[Any]) -> list[str]:
    """What could not be determined, with near-identical wording collapsed.

    Exact de-duplication is not enough and the real pack proved it: six
    sentences differing only in which receiver they named are six distinct
    strings, so they survived a de-duplication and filled six lines with one
    fact. Grouping is therefore by *kind* and the wording is factored inside
    it, which is the same mechanism the findings use.
    """
    lines: list[str] = []
    by_kind: dict[Any, list[Any]] = {}
    for uncertainty in uncertainties:
        by_kind.setdefault(uncertainty.kind, []).append(uncertainty)

    for group in by_kind.values():
        counted = _counted(group)
        statements = list(counted)
        shared, differing = _factored(statements)
        if len(statements) > 1 and shared and any(differing):
            lines.append(f"- **{_cell(shared)}**")
            named = " &middot; ".join(
                (
                    value
                    if counted[statement][1] == 1
                    else f"{value} (x{counted[statement][1]})"
                )
                for statement, value in zip(statements, differing)
            )
            lines.append(f"  {_cell(named)}")
            continue
        for statement in statements:
            subject, times = counted[statement]
            named = f"**{_cell(subject)}** -- " if subject else ""
            raised = "" if times == 1 else f"(raised {times} times) "
            lines.append(f"- {named}{raised}{_cell(statement)}")
    lines.append("")
    return lines


#: How much shared wording makes factoring worth doing. Below this the
#: heading is a fragment and the rows are whole sentences pretending to be
#: values, which is less readable than leaving them alone.
FACTOR_MINIMUM = 20


def _factored(texts: Sequence[str]) -> tuple[str, list[str]]:
    """The sentence a set of texts shares, and what each one adds to it.

    Purely mechanical: the common prefix and suffix, trimmed to word
    boundaries so a heading never ends mid-word. Returns the shared text
    with an ellipsis where the difference goes, and the differences in the
    order given. When there is too little in common it returns no shared
    text and the texts unchanged, and the caller lists them instead.
    """
    if len(set(texts)) == 1:
        return texts[0], ["" for _ in texts]

    prefix = _word_bounded(os.path.commonprefix(list(texts)), texts)
    rest = [text[len(prefix) :] for text in texts]
    reversed_suffix = os.path.commonprefix([text[::-1] for text in rest])
    suffix = _word_bounded(reversed_suffix[::-1], rest, from_end=True)

    if len(prefix) + len(suffix) < FACTOR_MINIMUM:
        return "", list(texts)

    differing = [
        text[len(prefix) : len(text) - len(suffix)] if suffix else text[len(prefix) :]
        for text in texts
    ]
    shared = f"{prefix.rstrip()} ... {suffix.lstrip()}".strip()
    return shared, [value.strip() for value in differing]


def _word_bounded(common: str, texts: Sequence[str], *, from_end: bool = False) -> str:
    """`common`, trimmed back to a word boundary.

    The raw common prefix of *deviated by 13.43* and *deviated by 10.62* is
    *deviated by 1*, which would leave `3.43` and `0.62` as the values --
    numbers that are not the numbers the rules reported.
    """
    if not common or any(len(common) == len(text) for text in texts):
        return common
    if from_end:
        cut = common.find(" ")
        return common[cut:] if cut != -1 else ""
    cut = common.rfind(" ")
    return common[: cut + 1] if cut != -1 else ""


def _grouped(findings: Sequence[Any]) -> dict[tuple[str, str], list[Any]]:
    """Findings under the `(rule_id, finding_type)` pair `ai-001` defines.

    The same pair `ai-008` resolves a citation on and `ai-002` groups its
    own citations by, so this introduces no vocabulary of its own. The rule
    id alone would collapse `anom-012`'s rate excess into `anom-010`'s
    discontinuities, which is the confusion the two-part key exists for.
    """
    groups: dict[tuple[str, str], list[Any]] = {}
    for finding in findings:
        groups.setdefault((finding.rule_id, finding.finding_type), []).append(finding)
    return groups


def _counted(uncertainties: Sequence[Any]) -> dict[str, tuple[str, int]]:
    """Each distinct statement once, with how many times it was raised."""
    counted: dict[str, tuple[str, int]] = {}
    for uncertainty in uncertainties:
        subject, times = counted.get(uncertainty.statement, (uncertainty.subject, 0))
        counted[uncertainty.statement] = (subject, times + 1)
    return counted


def _rendered(item: PackItem) -> str:
    """One hypothesis, in a shape that is the same for every arm."""
    h = item.hypothesis
    lines = [
        f"### Hypothesis {item.label}",
        "",
        f"**{h.hypothesis_title}**",
        "",
        f"Stated confidence: **{h.confidence.value}**",
        "",
        h.summary,
        "",
        "*Supporting evidence:*",
        "",
    ]
    lines += [
        f"- **{citation.rule_id} / {citation.finding_type}** -- {citation.statement}"
        for citation in h.supporting_evidence
    ]
    lines += ["", "*Uncertainty:*", ""]
    lines += [f"- {line}" for line in h.evidence_against_or_uncertainty] or ["- none"]
    lines += ["", "*Alternatives:*", ""]
    lines += [f"- {line}" for line in h.alternative_explanations]
    lines += ["", "*Recommended action:*", "", h.recommended_human_action, ""]
    return "\n".join(lines)


def _sheet(items: Sequence[PackItem]) -> str:
    """One blank row per item. No arm, no generator, no hint."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["item_id", "pack", "label", *DIMENSIONS, *JUDGEMENTS])
    for item in items:
        writer.writerow(
            [item.item_id, f"{item.bundle_id:05d}", item.label]
            + [""] * (len(DIMENSIONS) + len(JUDGEMENTS))
        )
    return out.getvalue()


def _key(items: Sequence[PackItem]) -> str:
    """Held separately, and joined only after both sheets are ingested."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["item_id", "bundle_id", "label", "arm"])
    for item in items:
        writer.writerow([item.item_id, item.bundle_id, item.label, item.arm.value])
    return out.getvalue()


def as_json(pack: ScoringPack) -> dict[str, Any]:
    """The pack's shape as figures, for the record rather than for a marker."""
    return {
        "bundles": pack.bundles,
        "items": len(pack.items),
        "items_per_bundle": pack.items_per_bundle,
        "dimensions": list(DIMENSIONS),
        "judgements": list(JUDGEMENTS),
        "values_per_rater": pack.values_per_rater,
    }


__all__ = [
    "BLINDING_GIVEAWAYS",
    "CAUSAL_CONNECTIVES",
    "GLOSSARY",
    "DIMENSIONS",
    "JUDGEMENTS",
    "SCORED_ORDINAL",
    "PackItem",
    "ScoringPack",
    "as_json",
    "build_pack",
]
