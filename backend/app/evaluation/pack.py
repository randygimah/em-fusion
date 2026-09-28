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
        hypotheses_md=_preamble(len(scored)) + "\n---\n\n".join(sections),
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
    """One pack, as Markdown a renderer survives.

    The first version emitted space-aligned plain text into a `.md` file.
    Two spaces of indent is neither a fence nor a code block nor a list, so
    every finding joined one paragraph and the alignment the layout rested
    on collapsed -- legible in an editor, unreadable everywhere else.
    """
    conclusion = _conclusion(bundle_id, bundle)
    start, end = bundle.time_window
    lines = [
        f"## Evidence pack {bundle_id:05d} -- {position} of {total}",
        "",
        "| | |",
        "|---|---|",
        f"| **Time window** | {start:%Y-%m-%d %H:%M} to {end:%H:%M} |",
        f"| **Subject** | {_cell(bundle.subject)} |",
        "| **Channels** | "
        + _cell(", ".join(str(c) for c in bundle.affected_channels))
        + " |",
        "",
        "**What the detection rules concluded**",
        "",
        f"> **{conclusion.rule_id} / {conclusion.finding_type}**"
        + (f" -- {_cell(conclusion.source)}" if conclusion.source else ""),
        ">",
        f"> {_cell(conclusion.finding)}",
        "",
    ]

    rest = [item for item in bundle.evidence if item is not conclusion]
    if rest:
        lines += ["**Findings behind that conclusion**", ""]
        for (rule_id, finding_type), group in _grouped(rest).items():
            noun = "finding" if len(group) == 1 else "findings"
            lines += [
                f"*{rule_id} / {finding_type}* -- {len(group)} {noun}",
                "",
                "| Source | What it found |",
                "|---|---|",
            ]
            # Every finding, individually. Grouping saves the re-reading; it
            # must not do the reading. A pack that summarised its own
            # findings would have done part of the work dimension 1 scores.
            lines += [
                f"| {_cell(item.source)} | {_cell(item.finding)} |" for item in group
            ]
            lines.append("")

    if bundle.known_uncertainties:
        lines += ["**What the rules could not determine**", ""]
        for statement, (subject, times) in _counted(bundle.known_uncertainties).items():
            raised = "" if times == 1 else f"(raised {times} times) "
            named = f"**{_cell(subject)}** -- " if subject else ""
            lines.append(f"- {named}{raised}{_cell(statement)}")
        lines.append("")

    for item in items:
        lines.append(_rendered(item))
    # The rule between packs is joined *between* sections and never appended
    # here. Appended, it lands after the last hypothesis only -- which makes
    # B's block end in something A's does not, and a formatting difference
    # between the two labels is a perfect classifier.
    return "\n".join(lines)


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
    """Each distinct statement once, with how many times it was raised.

    The first real pack carried the same one-reading RF-07 sentence three
    times, verbatim and adjacent. Repeating it says nothing the count does
    not, and it costs the marker three reads to learn that.
    """
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
    "DIMENSIONS",
    "JUDGEMENTS",
    "SCORED_ORDINAL",
    "PackItem",
    "ScoringPack",
    "as_json",
    "build_pack",
]
