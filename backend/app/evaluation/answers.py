"""The answer sheet for the blind scoring's second pass. Spec: eval-010.

`docs/scoring_rubric.md` tells each rater that once every pass-one score is in
they will be "given the correct answer for each evidence pack -- what the
system was actually looking at", and judge cause correctness and confidence
calibration against it. Nothing produced that answer until the first rater
reached pass two and found only the arm key. This renders it.

**The correct answers are sentences fixed per scenario type, not judgements
made per pack.** Each paraphrases `scn-002`'s definition of the type, which
was written before the campaign; the mixed type's carries its words
verbatim, "the correct hypothesis is that they cannot be distinguished". By
the time this sheet exists the author has read every explanation, so a sheet
that decided anything pack by pack would be the author scoring pass two for
the second rater.

**A pack is not always about its run's staged incident**, and the sheet says
which. A staged run still has a background, and a conclusion about a receiver
the staging never touched, or about another stretch of the hour, is marked
against "nothing was staged here" rather than against the run's sentence. The
test is mechanical: the conclusion names at least one staged receiver and its
window shares a moment with the staged one.

**Every value is copied from the record and none is computed** -- `eval-007`'s
rule for the pack, carried to the sheet that sits beside it. The one thing
derived is which staged aircraft the pack's own findings name, an
intersection a rater could make by eye.

**It is a separate file, and per pack rather than per explanation.** Merged
into the pack or the workbook it would sit in front of a rater during pass
one. It names neither label, carries nothing from the arm key, and is scanned
for arm vocabulary like every other file a marker reads.

Nothing here reaches a database. The sample, the records and the bundles
arrive as the caller read them, following `eval-004`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from app.dal.pseudonymise import PSEUDONYM_LENGTH
from app.detection.bundle import EvidenceBundle
from app.evaluation.pack import BLINDING_GIVEAWAYS


class AnswerSheetError(ValueError):
    """An input the sheet refuses to render, rather than render wrongly."""


#: What was actually happening, per scenario type, from `scn-002`. Only the
#: three types that produce a bundle: `normal-baseline` stages nothing and
#: `aircraft-coverage-gap`'s rule was never built, so either in a scored sample
#: means it is not the sample `eval-004` drew.
CORRECT_ANSWERS: Final[Mapping[str, str]] = {
    "gnss-degradation": (
        "Localised interference. The noise floor was raised on the GNSS L1 "
        "channel, or across all eight channels, at a group of neighbouring "
        "receivers, and aircraft inside the affected area kept reporting with "
        "their position frozen."
    ),
    "rf-sensor-fault": (
        "A fault in one receiver. Its readings deviated while its neighbours "
        "stayed nominal; nothing happened in the environment and no aircraft "
        "were affected."
    ),
    "ambiguous-mixed-evidence": (
        "Deliberately ambiguous. One receiver deviated while aircraft nearby "
        "stopped reporting in the same window, so a sensor fault and genuine "
        "localised interference are both consistent with the evidence, and "
        "the correct hypothesis is that they cannot be distinguished."
    ),
}

#: The answer for a pack whose conclusion is not about its run's staging.
NOT_STAGED: Final = (
    "Nothing was staged at the receivers this pack names during its window. "
    "The conclusion is about something the rules found elsewhere in the hour, "
    "not about the incident staged in this run."
)

#: How each track mode affected the aircraft it touched (`scn-002`).
_TRACK_EFFECT: Final[Mapping[str, str]] = {
    "freeze": "positions frozen",
    "suppress": "stopped reporting",
}

_HEADING = re.compile(r"^## Evidence pack (\d+) -- \d+ of \d+$", re.MULTILINE)
_PSEUDONYM = re.compile(rf"^AC-[0-9a-f]{{{PSEUDONYM_LENGTH}}}$")


def pack_order(hypotheses_md: str) -> tuple[int, ...]:
    """The bundle ids of the scoring pack, in the order it presents them."""
    order = tuple(int(found) for found in _HEADING.findall(hypotheses_md))
    if not order:
        raise AnswerSheetError(
            "the scoring pack holds no evidence packs, and an answer sheet for "
            "none would be an empty file that looks finished"
        )
    repeated = sorted({b for b in order if order.count(b) > 1})
    if repeated:
        raise AnswerSheetError(f"the scoring pack lists bundle(s) {repeated} twice")
    return order


def build_answer_sheet(
    *,
    order: Sequence[int],
    sample: Mapping[int, str],
    truths: Mapping[int, Mapping[str, Any]],
    bundles: Mapping[int, EvidenceBundle],
) -> str:
    """Render the sheet: one section per pack, in the pack's order.

    `sample` is the committed draw's scenario type per bundle; `truths` is the
    ground-truth record of each bundle's run, keyed by bundle; `bundles` are
    the stored bundles the pack rendered.
    """
    if len(set(order)) != len(order):
        raise AnswerSheetError("the pack order lists a bundle twice")
    unsampled = sorted(set(order) - set(sample))
    unpacked = sorted(set(sample) - set(order))
    if unsampled or unpacked:
        raise AnswerSheetError(
            f"the pack and the sample disagree: {unsampled} are in the pack "
            f"and not the sample, {unpacked} in the sample and not the pack. "
            "Every pack is answered from the draw eval-004 committed."
        )

    sections = [
        _section(
            bundle_id,
            position=position,
            total=len(order),
            scenario_type=sample[bundle_id],
            truth=truths.get(bundle_id),
            bundle=bundles.get(bundle_id),
        )
        for position, bundle_id in enumerate(order, start=1)
    ]
    sheet = _PREAMBLE + "\n---\n\n".join(sections)

    leaks = [word for word in BLINDING_GIVEAWAYS if word in sheet.lower()]
    if leaks:
        raise AnswerSheetError(
            f"the answer sheet names the arms {leaks}. A rater reads it between "
            "passes, and it would unblind the second one."
        )
    return sheet


_PREAMBLE: Final = (
    "# Answer sheet\n\n"
    "What was actually staged in the run behind each evidence pack, for the "
    "second pass of the scoring.\n\n"
    "**Open this only after you have entered every score of pass one.** The "
    "quality judgements are made before the answer is seen, because knowing "
    "it changes how good an explanation feels. Do not go back and change a "
    "pass one score.\n\n"
    "For each pack, judge **cause correctness** against *The correct answer* "
    "and **confidence calibration** against how strong the evidence in the "
    "pack was. Each section also says whether the pack's conclusion is about "
    "the incident staged in its run; where it is not, the correct answer "
    "says so.\n\n"
    "---\n\n"
)


def _section(
    bundle_id: int,
    *,
    position: int,
    total: int,
    scenario_type: str,
    truth: Mapping[str, Any] | None,
    bundle: EvidenceBundle | None,
) -> str:
    if scenario_type not in CORRECT_ANSWERS:
        raise AnswerSheetError(
            f"bundle {bundle_id} comes from a {scenario_type!r} run, which has no "
            "declared correct answer. Only the three types that produce a bundle "
            "can be in the scored sample."
        )
    if truth is None:
        raise AnswerSheetError(
            f"bundle {bundle_id}'s run has no ground-truth record to answer from"
        )
    if truth.get("scenario_type") != scenario_type:
        raise AnswerSheetError(
            f"bundle {bundle_id} was sampled as {scenario_type!r} but its run's "
            f"record says {truth.get('scenario_type')!r}"
        )
    if bundle is None:
        raise AnswerSheetError(
            f"bundle {bundle_id} was not supplied, so whether it is about the "
            "staged incident cannot be said"
        )

    staged_aircraft = [str(a) for a in truth.get("aircraft") or []]
    named = [a for a in staged_aircraft if not _PSEUDONYM.match(a)]
    if named:
        raise AnswerSheetError(
            f"bundle {bundle_id}'s record names {len(named)} staged aircraft by "
            "something other than a pseudonym; a source identifier never "
            "reaches a committed file (dal-004)"
        )

    receivers = tuple(bundle.subject.split(", "))
    sensors = [str(s) for s in truth.get("sensors") or []]
    window = truth.get("window")
    staged_from = datetime.fromisoformat(window["start"]) if window else None
    staged_to = datetime.fromisoformat(window["end"]) if window else None
    start, end = bundle.time_window
    about = (
        staged_from is not None
        and staged_to is not None
        and any(receiver in sensors for receiver in receivers)
        and start < staged_to
        and staged_from < end
    )

    sources = {part for item in bundle.evidence for part in item.source.split(", ")}
    in_pack = [a for a in staged_aircraft if a in sources]
    mode = truth.get("track_mode")
    channels = [str(c) for c in truth.get("channels") or []]
    elevation = truth.get("elevation_db")

    rows = [
        ("About the staged incident", "Yes" if about else "No"),
        ("This pack", f"{_when(start, end)} &middot; {', '.join(receivers)}"),
        ("Scenario", scenario_type),
        ("Staged receivers", ", ".join(sensors) or "none"),
        (
            "Band",
            f"{truth.get('spectral_extent')} &middot; "
            f"channel{'s' if len(channels) != 1 else ''} {', '.join(channels)}",
        ),
        (
            "Staged window",
            (
                _when(staged_from, staged_to)
                if staged_from is not None and staged_to is not None
                else "none"
            ),
        ),
        ("Strength", "not recorded" if elevation is None else f"{elevation} dB"),
        (
            "Staged aircraft",
            (
                f"{_TRACK_EFFECT.get(str(mode), str(mode))}: "
                f"{', '.join(staged_aircraft)}"
                if mode and staged_aircraft
                else "none"
            ),
        ),
        ("Staged aircraft in this pack", ", ".join(in_pack) or "none"),
    ]
    return "\n".join(
        [
            f"## Evidence pack {bundle_id:05d} -- {position} of {total}",
            "",
            "**The correct answer.** "
            + (CORRECT_ANSWERS[scenario_type] if about else NOT_STAGED),
            "",
            "| | |",
            "|---|---|",
            *(f"| **{label}** | {value} |" for label, value in rows),
            "",
        ]
    )


def _when(start: datetime, end: datetime) -> str:
    """A window as the pack's own *When* row writes it."""
    return f"{start:%Y-%m-%d %H:%M} to {end:%H:%M}"


__all__ = [
    "CORRECT_ANSWERS",
    "NOT_STAGED",
    "AnswerSheetError",
    "build_answer_sheet",
    "pack_order",
]
