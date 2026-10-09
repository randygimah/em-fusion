"""The answer sheet for the blind scoring's second pass. Spec: eval-010.

The rubric promises each rater "the correct answer for each evidence pack --
what the system was actually looking at" once pass one is done, and nothing
produced it. This is that sheet: one section per pack, in the pack's own order
and headings, saying what was staged in the pack's run and whether the pack's
conclusion is about it.

**The correct answers are fixed sentences, not judgements made now.** One per
scenario type, taken from `scn-002`'s definition, which predates the campaign.
The author has read every explanation by the time this is rendered, so a
sheet that decided anything per pack would be the author scoring pass two for
the second rater.

**These tests run against bundles the real builder produced**, the pack's own
rule (`ai-002`, `eval-004`): a hand-written bundle tests the author's model of
one.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.detection.bundle import EvidenceBundle
from app.evaluation.pack import BLINDING_GIVEAWAYS
from tests.test_ai_template import fault_bundle, zone_bundle
from tests.test_evb_bundle import END, START


def _answers() -> Any:
    """The module under test, imported late so a missing module fails each test
    rather than the whole file at collection."""
    from app.evaluation import answers

    return answers


SPEC = Path(__file__).resolve().parents[2] / "docs" / "spec.jsonl"

#: Pseudonyms in the shape the DAL produces (`dal-004`).
STAGED = "AC-48089ab4e5a9"
ALSO_STAGED = "AC-3c6444b1e2f0"

ZONE_ID = 248
FAULT_ID = 250


def _truth(
    scenario_type: str = "gnss-degradation",
    *,
    sensors: Sequence[str] = ("RF-03", "RF-04"),
    channels: Sequence[int] = (4,),
    extent: str = "narrowband",
    start: datetime = START,
    end: datetime = END,
    elevation: float = 12.5,
    mode: str | None = "freeze",
    aircraft: Sequence[str] = (STAGED, ALSO_STAGED),
) -> dict[str, Any]:
    """A run's ground-truth record, in the shape `scn-002` writes it."""
    return {
        "scenario_type": scenario_type,
        "seed": 7,
        "spectral_extent": extent,
        "sensors": list(sensors),
        "channels": list(channels),
        "elevation_db": elevation,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "track_mode": mode,
        "aircraft": list(aircraft),
    }


def _fault_truth(**kw: Any) -> dict[str, Any]:
    kw.setdefault("sensors", ("RF-03",))
    kw.setdefault("mode", None)
    kw.setdefault("aircraft", ())
    return _truth("rf-sensor-fault", **kw)


def _sheet(
    *,
    order: Sequence[int] = (ZONE_ID, FAULT_ID),
    sample: Mapping[int, str] | None = None,
    truths: Mapping[int, Mapping[str, Any]] | None = None,
    bundles: Mapping[int, EvidenceBundle] | None = None,
) -> str:
    result: str = _answers().build_answer_sheet(
        order=order,
        sample=(
            {ZONE_ID: "gnss-degradation", FAULT_ID: "rf-sensor-fault"}
            if sample is None
            else sample
        ),
        truths=(
            {ZONE_ID: _truth(), FAULT_ID: _fault_truth()} if truths is None else truths
        ),
        bundles=(
            {ZONE_ID: zone_bundle(), FAULT_ID: fault_bundle()}
            if bundles is None
            else bundles
        ),
    )
    return result


def _section(sheet: str, bundle_id: int) -> str:
    """One pack's section of the sheet."""
    [found] = re.findall(
        rf"^## Evidence pack {bundle_id:05d} -- .*?(?=^## |\Z)",
        sheet,
        flags=re.MULTILINE | re.DOTALL,
    )
    return str(found)


def _row(section: str, label: str) -> str:
    """The value in a section's table row labelled `label`."""
    [value] = re.findall(rf"^\| \*\*{re.escape(label)}\*\* \| (.*) \|$", section, re.M)
    return str(value)


# ------------------------------------------------------------ the pack's order


def test_the_pack_order_is_read_from_the_packs_own_headings() -> None:
    # spec: eval-010 -- the sheet follows hypotheses.md, never its own order.
    md = (
        "# Hypothesis scoring pack\n\n## Terms used in these packs\n\n"
        "## Evidence pack 00262 -- 1 of 2\n\ntext\n\n---\n\n"
        "## Evidence pack 00250 -- 2 of 2\n\ntext\n"
    )

    assert tuple(_answers().pack_order(md)) == (262, 250)


def test_a_pack_listed_twice_in_the_pack_is_refused() -> None:
    # spec: eval-010 -- a pack present twice.
    md = "## Evidence pack 00250 -- 1 of 2\n\n## Evidence pack 00250 -- 2 of 2\n"

    with pytest.raises(_answers().AnswerSheetError):
        _answers().pack_order(md)


def test_a_document_with_no_packs_is_refused() -> None:
    # spec: eval-010 -- an empty order would render an empty sheet that looks done.
    with pytest.raises(_answers().AnswerSheetError):
        _answers().pack_order("# Hypothesis scoring pack\n")


# ------------------------------------------------------------------- the sheet


def test_one_section_per_pack_in_the_packs_order_and_headings() -> None:
    # spec: eval-010 -- headed exactly as hypotheses.md heads the pack.
    sheet = _sheet(order=(FAULT_ID, ZONE_ID))

    headings = re.findall(r"^## Evidence pack .*$", sheet, flags=re.MULTILINE)
    assert headings == [
        "## Evidence pack 00250 -- 1 of 2",
        "## Evidence pack 00248 -- 2 of 2",
    ]


def test_the_sheet_says_when_to_open_it() -> None:
    # spec: eval-010 -- the rubric: quality judgements are made before the
    # answer is seen, so the sheet itself says so on its first lines.
    head = _sheet().split("## Evidence pack", 1)[0]

    assert head.startswith("# Answer sheet")
    assert "only after" in head.lower()
    assert "pass one" in head.lower()


def test_the_sheet_names_no_explanation_and_no_arm() -> None:
    # spec: eval-010 -- per pack, never per explanation, and nothing from the
    # arm key.
    sheet = _sheet()

    assert not re.search(r"\b\d{5}-[AB]\b", sheet)
    assert not re.search(r"\b(explanation|hypothesis) [AB]\b", sheet, re.I)
    assert not [word for word in BLINDING_GIVEAWAYS if word in sheet.lower()]


# ---------------------------------------------------------- the correct answer


def test_each_scenario_type_that_produces_a_bundle_has_one_sentence() -> None:
    # spec: eval-010 -- declared once, for exactly the three types a scored
    # sample can hold.
    assert set(_answers().CORRECT_ANSWERS) == {
        "gnss-degradation",
        "rf-sensor-fault",
        "ambiguous-mixed-evidence",
    }


def test_the_ambiguous_answer_is_scn_002s_own_pre_campaign_wording() -> None:
    # spec: eval-010, scn-002 -- the correct hypothesis for the mixed scenario
    # was written down before the campaign, and the sheet quotes it rather than
    # deciding it after the explanations were read.
    phrase = "cannot be distinguished"
    [scn_002] = [
        json.loads(line)
        for line in SPEC.read_text().splitlines()
        if '"id": "scn-002"' in line
    ]

    assert phrase in scn_002["description"]
    assert phrase in _answers().CORRECT_ANSWERS["ambiguous-mixed-evidence"]


def test_a_pack_about_its_staged_incident_gets_its_types_sentence() -> None:
    # spec: eval-010 -- (a), for each type.
    answers = _answers()
    sheet = _sheet(
        sample={ZONE_ID: "gnss-degradation", FAULT_ID: "ambiguous-mixed-evidence"},
        truths={
            ZONE_ID: _truth(),
            FAULT_ID: _truth(
                "ambiguous-mixed-evidence", sensors=("RF-03",), mode="suppress"
            ),
        },
    )

    assert answers.CORRECT_ANSWERS["gnss-degradation"] in _section(sheet, ZONE_ID)
    assert answers.CORRECT_ANSWERS["ambiguous-mixed-evidence"] in _section(
        sheet, FAULT_ID
    )
    assert answers.CORRECT_ANSWERS["rf-sensor-fault"] in _section(_sheet(), FAULT_ID)


def test_a_pack_about_its_staged_incident_says_so() -> None:
    # spec: eval-010 -- (c): a staged receiver named, the windows overlapping.
    sheet = _sheet()

    assert _row(_section(sheet, ZONE_ID), "About the staged incident") == "Yes"
    assert _row(_section(sheet, FAULT_ID), "About the staged incident") == "Yes"


def test_a_pack_naming_no_staged_receiver_is_not_about_the_staged_incident() -> None:
    # spec: eval-010 -- the failure case: a background conclusion in a staged
    # run marked against the staged event.
    answers = _answers()
    sheet = _sheet(
        truths={ZONE_ID: _truth(), FAULT_ID: _fault_truth(sensors=("RF-05",))}
    )
    section = _section(sheet, FAULT_ID)

    assert _row(section, "About the staged incident") == "No"
    assert answers.NOT_STAGED in section
    assert answers.CORRECT_ANSWERS["rf-sensor-fault"] not in section


def test_a_pack_outside_the_staged_window_is_not_about_the_staged_incident() -> None:
    # spec: eval-010 -- the right receiver at the wrong time is not the event.
    later = END + timedelta(minutes=5)
    sheet = _sheet(
        truths={
            ZONE_ID: _truth(),
            FAULT_ID: _fault_truth(start=later, end=later + timedelta(minutes=5)),
        }
    )
    section = _section(sheet, FAULT_ID)

    assert _row(section, "About the staged incident") == "No"
    assert _answers().NOT_STAGED in section


def test_windows_that_only_touch_do_not_overlap() -> None:
    # spec: eval-010 -- a staging starting the instant the pack's window ends
    # shares no moment with it.
    sheet = _sheet(
        truths={
            ZONE_ID: _truth(),
            FAULT_ID: _fault_truth(start=END, end=END + timedelta(minutes=5)),
        }
    )

    assert _row(_section(sheet, FAULT_ID), "About the staged incident") == "No"


# ------------------------------------------------------------ what was staged


def test_the_staged_facts_are_copied_from_the_record() -> None:
    # spec: eval-010 -- (b): every value copied, none computed, the window in
    # the pack's own "When" format.
    section = _section(_sheet(), ZONE_ID)

    assert _row(section, "Scenario") == "gnss-degradation"
    assert _row(section, "Staged receivers") == "RF-03, RF-04"
    assert _row(section, "Band") == "narrowband &middot; channel 4"
    assert _row(section, "Staged window") == "2022-06-27 12:00 to 12:05"
    assert _row(section, "Strength") == "12.5 dB"


def test_a_broadband_staging_lists_every_channel_it_touched() -> None:
    # spec: eval-010
    truths = {
        ZONE_ID: _truth(extent="broadband", channels=range(8)),
        FAULT_ID: _fault_truth(),
    }

    assert (
        _row(_section(_sheet(truths=truths), ZONE_ID), "Band")
        == "broadband &middot; channels 0, 1, 2, 3, 4, 5, 6, 7"
    )


def test_how_aircraft_were_affected_follows_the_track_mode() -> None:
    # spec: eval-010 -- frozen for interference, stopped for the mixed type,
    # none for a fault.
    sheet = _sheet(
        sample={ZONE_ID: "gnss-degradation", FAULT_ID: "ambiguous-mixed-evidence"},
        truths={
            ZONE_ID: _truth(),
            FAULT_ID: _truth(
                "ambiguous-mixed-evidence",
                sensors=("RF-03",),
                mode="suppress",
                aircraft=(STAGED,),
            ),
        },
    )

    assert _row(_section(sheet, ZONE_ID), "Staged aircraft") == (
        f"positions frozen: {STAGED}, {ALSO_STAGED}"
    )
    assert _row(_section(sheet, FAULT_ID), "Staged aircraft") == (
        f"stopped reporting: {STAGED}"
    )
    assert _row(_section(_sheet(), FAULT_ID), "Staged aircraft") == "none"


def test_the_staged_aircraft_this_pack_names_are_listed() -> None:
    # spec: eval-010 -- which of the staged aircraft appear in this pack's
    # findings. The zone bundle names STAGED and one aircraft never staged.
    section = _section(_sheet(), ZONE_ID)

    assert _row(section, "Staged aircraft in this pack") == STAGED
    assert _row(_section(_sheet(), FAULT_ID), "Staged aircraft in this pack") == (
        "none"
    )


# ------------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    "case",
    (
        "pack-not-sampled",
        "sampled-not-in-pack",
        "no-truth",
        "type-differs",
        "no-bundle",
        "unanswerable-type",
    ),
)
def test_an_inconsistent_input_is_refused_rather_than_rendered(case: str) -> None:
    # spec: eval-010 -- the failure cases: every pack answered from its own
    # run's record, the sample being the one eval-004 drew.
    kwargs: dict[str, Any] = {
        "pack-not-sampled": {"sample": {ZONE_ID: "gnss-degradation"}},
        "sampled-not-in-pack": {"order": (ZONE_ID,)},
        "no-truth": {"truths": {ZONE_ID: _truth()}},
        "type-differs": {
            "truths": {
                ZONE_ID: _truth(),
                FAULT_ID: _truth("ambiguous-mixed-evidence", sensors=("RF-03",)),
            }
        },
        "no-bundle": {"bundles": {ZONE_ID: zone_bundle()}},
        "unanswerable-type": {
            "sample": {ZONE_ID: "gnss-degradation", FAULT_ID: "normal-baseline"},
            "truths": {
                ZONE_ID: _truth(),
                FAULT_ID: _truth("normal-baseline", sensors=(), mode=None),
            },
        },
    }[case]

    with pytest.raises(_answers().AnswerSheetError):
        _sheet(**kwargs)


def test_a_staged_aircraft_not_named_by_pseudonym_is_refused() -> None:
    # spec: eval-010, dal-004 -- a source identifier never reaches the sheet.
    truths = {ZONE_ID: _truth(aircraft=("4b1805",)), FAULT_ID: _fault_truth()}

    with pytest.raises(_answers().AnswerSheetError):
        _sheet(truths=truths)


def test_arm_vocabulary_in_the_sheet_is_refused() -> None:
    # spec: eval-010 -- the guard fired at a real leak, so it is known to bite:
    # the staged receivers are rendered, and one is named after an arm.
    truths = {
        ZONE_ID: _truth(sensors=("RF-03", "Template-9")),
        FAULT_ID: _fault_truth(),
    }

    with pytest.raises(_answers().AnswerSheetError):
        _sheet(truths=truths)
