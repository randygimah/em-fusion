"""The workbook a marker actually scores in. Spec: eval-008.

`eval-004` exports a CSV. A CSV asks a rater to type a bare number into an
unlabelled column with nothing on screen saying what the number means, forty
times, and then twice more per item on a second pass. Every one of those
typings is an opportunity to enter a 4 -- which the pre-registered analysis
has no anchor for -- or to score the row above the one being read.

**A rendering of the same rows, never a second source.** The CSV stays the
archival and machine-readable form `eval-006` ingests; both come out of one
pass over one list of `PackItem`. A workbook built from its own traversal is
a second place for the two to disagree, and the disagreement would surface as
`eval-006` ingesting rows nobody scored.

**The anchors travel with the sheet.** The rubric's handout is a separate
document, and a rater flipping between two documents forty times drifts
toward scoring on memory of the anchors rather than on the anchors. They are
carried on a second sheet and again as a note on each column heading, which
costs nothing and removes the flipping.

**The blinding check follows the artefact.** `eval-004` scans what the marker
reads for the arm vocabulary. Adding a second file the marker reads without
extending that scan does not keep the guarantee, it relocates the leak to the
file nobody looked at -- so the test here covers cell values, headings, sheet
names, notes and the document properties, the last being a place a leak would
be invisible on screen and still sit in the file.

Nothing here reaches a database or a model.
"""

from __future__ import annotations

import io
from typing import Any, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.ai.service import ConfigurationError
from app.evaluation.pack import DIMENSIONS, JUDGEMENTS, PackItem

#: What the sheet accepts, and it is the **whole** 1-5 range.
#:
#: Corrected before any scoring: an earlier version of this module offered
#: only 1/3/5, on the reasoning that those are the points carrying a worded
#: anchor. `docs/scoring_rubric.md` Part A says the opposite in as many
#: words -- *"use 2 and 4 for anything in between"* -- so that dropdown
#: would have refused values the pre-registered instrument invites, and
#: `eval-006` reports **quadratic-weighted** kappa, which is computed over
#: the scale actually used. A narrowed scale is therefore not a stricter
#: sheet, it is a silent change to the pre-registered analysis.
SCALE: tuple[int, ...] = (1, 2, 3, 4, 5)

#: The three points the rubric words. The others are explicitly "anything in
#: between", so they need no anchor and their absence is not a gap.
ANCHORED: tuple[int, ...] = (1, 3, 5)

SHEET = "Scores"
ANCHOR_SHEET = "How to score"

#: `docs/scoring_rubric.md` Part A, transcribed rather than paraphrased. The
#: heading is what the scorer reads on the handout; the field name underneath
#: is what `eval-006` joins on and is never shown as a column heading.
ANCHORS: dict[str, dict[Any, Any]] = {
    "evidence_use": {
        "heading": "Evidence use",
        "question": "Does it actually reason from the evidence, or just repeat it?",
        1: (
            "Repeats the findings back, or ignores them. No reasoning connects "
            "the evidence to the conclusion."
        ),
        3: (
            "Uses the findings correctly, but in a generic way -- the same words "
            "would fit many different situations."
        ),
        5: (
            "Reasons from these specific findings, connects them to each other, "
            "and shows how they lead to the conclusion."
        ),
    },
    "uncertainty": {
        "heading": "Uncertainty",
        "question": "Is it honest about what it doesn't know?",
        1: (
            "No uncertainty stated, or a boilerplate disclaimer that would apply "
            "to any output whatsoever."
        ),
        3: "Names a real uncertainty, but doesn't say what difference it makes.",
        5: (
            "Names specific uncertainties and explains how each one weakens or "
            "qualifies the conclusion."
        ),
    },
    "alternatives": {
        "heading": "Alternative explanations",
        "question": "Does it offer genuine competing possibilities?",
        1: (
            "None offered, or the 'alternatives' are restatements of the main "
            "explanation."
        ),
        3: (
            "Plausible alternatives listed, but nothing said about how you'd "
            "tell them apart."
        ),
        5: (
            "Genuine competing explanations, with an indication of what evidence "
            "would distinguish them."
        ),
    },
    "actionability": {
        "heading": "Recommended action",
        "question": "Could an analyst act on this?",
        1: (
            "No action, or something so generic it carries no information "
            "('investigate further')."
        ),
        3: "Sensible, but non-specific -- right direction, no concrete step.",
        5: (
            "A specific next step, appropriate to this evidence, that an analyst "
            "could take immediately."
        ),
    },
    "overall_usefulness": {
        "heading": "Overall usefulness",
        "question": (
            "Would this help an analyst working under time pressure? Your overall "
            "judgement, not an average of the other four."
        ),
        1: "Would waste time, or point in the wrong direction.",
        3: "Mildly helpful. Saves a little work.",
        5: "Would meaningfully speed up correct triage.",
    },
    "cause_correctness": {
        "heading": "Cause correctness",
        "question": (
            "SECOND PASS ONLY. Does the explanation identify what was actually "
            "happening?"
        ),
        "options": ("Correct", "Partly correct", "Incorrect"),
    },
    "confidence_calibration": {
        "heading": "Confidence calibration",
        "question": (
            "SECOND PASS ONLY. Given how strong the evidence actually was, is "
            "the stated confidence right? A confident-sounding hypothesis built "
            "on weak evidence is Too high even if it turned out correct."
        ),
        "options": ("Too low", "About right", "Too high"),
    },
}

IDENTIFIERS = ("Item", "Pack", "Label")

_HEAD = Font(bold=True, color="FFFFFF")
_HEAD_FILL = PatternFill("solid", fgColor="1F3A5F")
_WRAP = Alignment(vertical="top", wrap_text=True)
_LOCKED = Protection(locked=True)
_OPEN = Protection(locked=False)


def _checked(
    dimensions: Sequence[str], judgements: Sequence[str], scale: Sequence[int]
) -> None:
    """Refuse a sheet that would collect values the rubric cannot read."""
    if tuple(scale) != SCALE:
        raise ConfigurationError(
            f"the scoring scale {tuple(scale)!r} is not the rubric's {SCALE!r}. "
            "A sheet offering another scale collects values the pre-registered "
            "analysis was not specified over -- and since eval-006 reports "
            "quadratic-weighted kappa, which is computed across the scale that "
            "was used, narrowing it is a change to the analysis rather than a "
            "stricter sheet."
        )
    for name in (*dimensions, *judgements):
        anchor = ANCHORS.get(name)
        if anchor is None:
            raise ConfigurationError(
                f"{name!r} has no anchor entry in the rubric transcription. "
                "Exported anyway it becomes a column whose dropdown offers "
                "nothing, which reads to the scorer as a broken file and to a "
                "reader of the results as a dimension nobody scored."
            )
        # Anchors are owed on the three worded points only. Demanding one
        # for 2 and 4 would contradict the rubric, which calls them
        # "anything in between" and words them on purpose not at all.
        wanted = ["options"] if name in judgements else list(ANCHORED)
        missing = [key for key in wanted if key not in anchor]
        if missing:
            raise ConfigurationError(
                f"{name!r} is missing the anchor(s) {missing!r}. A scored column "
                "without its full anchor set cannot be scored consistently, and "
                "the inconsistency is invisible in the results."
            )


def score_sheet_workbook(
    items: Sequence[PackItem],
    *,
    dimensions: Sequence[str] = DIMENSIONS,
    judgements: Sequence[str] = JUDGEMENTS,
    scale: Sequence[int] = SCALE,
) -> bytes:
    """The marker's workbook: one row per item, nothing naming an arm."""
    _checked(dimensions, judgements, scale)

    book = Workbook()
    # Set explicitly rather than left to the library's default, because the
    # properties are a place a leak would sit in the file and never appear on
    # screen -- which is exactly the kind of leak a visual check misses.
    book.properties.creator = "EM Fusion"
    book.properties.title = "Hypothesis scoring"

    sheet = book.active
    sheet.title = SHEET
    scored = [*dimensions, *judgements]

    sheet.append([*IDENTIFIERS, *(ANCHORS[name]["heading"] for name in scored)])
    for cell in sheet[1]:
        cell.font, cell.fill, cell.alignment = _HEAD, _HEAD_FILL, _WRAP
    for offset, name in enumerate(scored):
        cell = sheet.cell(row=1, column=len(IDENTIFIERS) + 1 + offset)
        cell.comment = _note(name, scale)

    for item in items:
        sheet.append(
            [item.item_id, f"{item.bundle_id:05d}", item.label] + [None] * len(scored)
        )

    # Locked by default so the identifiers cannot be typed over -- the one
    # edit that silently destroys the join `eval-006` makes between two
    # raters' sheets and the key. The scored cells are the only ones opened.
    last = len(items) + 1
    for row in sheet.iter_rows(min_row=1, max_row=last):
        for cell in row:
            cell.protection = _LOCKED
    for offset in range(len(scored)):
        column = len(IDENTIFIERS) + 1 + offset
        for row in range(2, last + 1):
            sheet.cell(row=row, column=column).protection = _OPEN

    if items:
        for offset, name in enumerate(scored):
            letter = get_column_letter(len(IDENTIFIERS) + 1 + offset)
            allowed = (
                ANCHORS[name]["options"]
                if name in judgements
                else [str(value) for value in scale]
            )
            rule = DataValidation(
                type="list",
                formula1='"' + ",".join(allowed) + '"',
                allow_blank=True,
                showErrorMessage=True,
                errorTitle="Not on the scale",
                error="Choose one of: " + ", ".join(allowed),
            )
            sheet.add_data_validation(rule)
            rule.add(f"{letter}2:{letter}{last}")

    sheet.freeze_panes = "D2"
    sheet.protection.sheet = True
    # Without this the protection also blocks selecting a cell to type in.
    sheet.protection.selectUnlockedCells = False
    for letter, width in zip("ABC", (12, 10, 8)):
        sheet.column_dimensions[letter].width = width
    for offset in range(len(scored)):
        sheet.column_dimensions[
            get_column_letter(len(IDENTIFIERS) + 1 + offset)
        ].width = 16

    _anchor_sheet(book, dimensions, judgements, scale)
    return _bytes(book)


def _note(name: str, scale: Sequence[int]) -> Any:
    """The column's anchors, on the heading the scorer is looking at."""
    from openpyxl.comments import Comment

    anchor = ANCHORS[name]
    lines = [str(anchor["heading"]), str(anchor["question"]), ""]
    if "options" in anchor:
        lines += [f"- {option}" for option in anchor["options"]]
    else:
        lines += [f"{value} = {anchor[value]}" for value in ANCHORED]
        lines.append("Use 2 and 4 for anything in between.")
    comment = Comment("\n".join(lines), "EM Fusion")
    comment.width, comment.height = 380, 200
    return comment


def _anchor_sheet(
    book: Workbook,
    dimensions: Sequence[str],
    judgements: Sequence[str],
    scale: Sequence[int],
) -> None:
    """Every anchor in full, so the handout need not be open beside this."""
    sheet = book.create_sheet(ANCHOR_SHEET)
    sheet.append(["Dimension", "Score", "What that score means"])
    for cell in sheet[1]:
        cell.font, cell.fill, cell.alignment = _HEAD, _HEAD_FILL, _WRAP

    for name in dimensions:
        anchor = ANCHORS[name]
        sheet.append([str(anchor["heading"]), "", str(anchor["question"])])
        sheet.cell(row=sheet.max_row, column=1).font = Font(bold=True)
        for value in ANCHORED:
            sheet.append(["", value, str(anchor[value])])
        sheet.append(["", "2 and 4", "Anything in between the worded points."])
    for name in judgements:
        anchor = ANCHORS[name]
        sheet.append([str(anchor["heading"]), "", str(anchor["question"])])
        sheet.cell(row=sheet.max_row, column=1).font = Font(bold=True)
        for option in anchor["options"]:
            sheet.append(["", option, ""])

    sheet.column_dimensions["A"].width = 24
    sheet.column_dimensions["B"].width = 14
    sheet.column_dimensions["C"].width = 110
    for row in sheet.iter_rows(min_row=2):
        row[2].alignment = _WRAP
    sheet.freeze_panes = "A2"


def arm_key_workbook(items: Sequence[PackItem]) -> bytes:
    """The key, as its own file.

    A separate workbook and never a tab on the sheet being scored in: a tab
    is one click away, and the point of holding the key back is that it
    cannot be reached while a score is being entered.
    """
    book = Workbook()
    book.properties.creator = "EM Fusion"
    book.properties.title = "Arm key -- held back until both sheets are in"

    sheet = book.active
    sheet.title = "Key"
    sheet.append(["item_id", "bundle_id", "label", "arm"])
    for cell in sheet[1]:
        cell.font, cell.fill = _HEAD, _HEAD_FILL
    for item in items:
        sheet.append([item.item_id, item.bundle_id, item.label, item.arm.value])
    sheet.freeze_panes = "A2"
    for letter, width in zip("ABCD", (14, 12, 8, 14)):
        sheet.column_dimensions[letter].width = width
    return _bytes(book)


def _bytes(book: Workbook) -> bytes:
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


__all__ = [
    "ANCHORED",
    "ANCHORS",
    "ANCHOR_SHEET",
    "SCALE",
    "SHEET",
    "arm_key_workbook",
    "score_sheet_workbook",
]
