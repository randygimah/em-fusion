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

from app.ai.campaign import CampaignRecord
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
    record: CampaignRecord,
    bundles: Sequence[tuple[int, EvidenceBundle]],
    hypotheses: Mapping[int, Hypothesis],
    seed: int,
) -> ScoringPack:
    """Render the pack, the blank sheet, and the key held separately."""
    held = dict(bundles)
    scored = _scored_generations(record)

    items: list[PackItem] = []
    sections: list[str] = []
    for bundle_id in sorted(scored):
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
        sections.append(_section(bundle_id, held[bundle_id], paired))

    return ScoringPack(
        hypotheses_md=_preamble() + "\n".join(sections),
        score_sheet_csv=_sheet(items),
        arm_key_csv=_key(items),
        items=tuple(items),
        bundles=len(scored),
        items_per_bundle=len(LABELS),
    )


def _scored_generations(
    record: CampaignRecord,
) -> dict[int, dict[GeneratorKind, int]]:
    """Each bundle's scored row per arm, taken by **ordinal**.

    By ordinal and never by position, which would silently export a
    different generation on any bundle whose rows were written in another
    order -- and on a bundle where generation 1 fell back, that is exactly
    the substitution the pre-registration forbids.
    """
    found: dict[int, dict[GeneratorKind, int]] = {}
    for generation in record.generations:
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


def _preamble() -> str:
    return (
        "# Hypothesis scoring pack\n\n"
        "Under each evidence pack are two short explanations, labelled A and "
        "B. They were produced by two different systems. You are not told "
        "which is which, and the labels are reshuffled on every pack -- A "
        "here has nothing to do with A on the next page.\n\n"
        "Read the evidence pack first, then both explanations, then score "
        "each one on its own terms against `score_sheet.csv`.\n\n"
        "Two explanations under one pack may occasionally be identical or "
        "nearly so. That is expected rather than a fault in the pack.\n\n"
        "---\n\n"
    )


def _section(bundle_id: int, bundle: EvidenceBundle, items: Sequence[PackItem]) -> str:
    lines = [f"## Evidence pack {bundle_id:05d}\n"]
    start, end = bundle.time_window
    lines.append(f"Time window:   {start:%Y-%m-%d %H:%M} to {end:%H:%M}")
    lines.append(f"Subject:       {bundle.subject}")
    lines.append(
        f"Channels:      {', '.join(str(c) for c in bundle.affected_channels)}"
    )
    lines.append("\nFindings:")
    for finding in bundle.evidence:
        lines.append(
            f"  {finding.rule_id:<20} {finding.finding_type:<28} {finding.finding}"
        )
    if bundle.known_uncertainties:
        lines.append("\nKnown uncertainties:")
        for uncertainty in bundle.known_uncertainties:
            lines.append(f"  {uncertainty.statement}")
    lines.append("")
    for item in items:
        lines.append(_rendered(item))
    return "\n".join(lines)


def _rendered(item: PackItem) -> str:
    """One hypothesis, in a shape that is the same for every arm."""
    h = item.hypothesis
    lines = [
        f"### Hypothesis {item.label}",
        "",
        f"**{h.hypothesis_title}** — Confidence: {h.confidence.value}",
        "",
        h.summary,
        "",
        "*Supporting evidence:*",
    ]
    lines += [
        f"- {citation.rule_id} / {citation.finding_type}: {citation.statement}"
        for citation in h.supporting_evidence
    ]
    lines += ["", "*Uncertainty:*"]
    lines += [f"- {line}" for line in h.evidence_against_or_uncertainty] or ["- none"]
    lines += ["", "*Alternatives:*"]
    lines += [f"- {line}" for line in h.alternative_explanations]
    lines += ["", "*Recommended action:*", h.recommended_human_action, ""]
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
    "DIMENSIONS",
    "JUDGEMENTS",
    "SCORED_ORDINAL",
    "PackItem",
    "ScoringPack",
    "as_json",
    "build_pack",
]
