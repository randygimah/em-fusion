"""The workbook a marker actually scores in. Spec: eval-008.

A bare CSV asks a rater to type a number into an unlabelled column with
nothing on screen saying what the number means, forty times, twice over.
Every one of those typings is a chance to enter a 4 the pre-registered
analysis has no anchor for, or to score the wrong row.

**The workbook is a rendering of the same rows, never a second source.** The
CSV stays the archival and machine-readable form that `eval-006` ingests, and
both come out of one pass over one list, so the two cannot drift.

**The blinding check has to follow the artefact.** `eval-004` scans what the
marker reads for the arm vocabulary. Adding a second file the marker reads
and not scanning it simply moves the leak to the file nobody looked at, so
the scan here covers cell values, headers, sheet names, notes and the
document properties, which are a place a leak would be invisible on screen.
"""

from __future__ import annotations

import io

import openpyxl
import pytest

from app.ai.service import ConfigurationError
from app.evaluation.pack import BLINDING_GIVEAWAYS, DIMENSIONS, JUDGEMENTS
from app.evaluation.workbook import (
    ANCHORS,
    SCALE,
    arm_key_workbook,
    score_sheet_workbook,
)
from tests.test_eval_pack import packed

SHEET = "Scores"


def opened(payload: bytes):
    return openpyxl.load_workbook(io.BytesIO(payload))


def sheet_of(pack):
    return opened(score_sheet_workbook(pack.items))[SHEET]


# --------------------------------------------------------------- the rows


def test_the_workbook_carries_one_row_per_item_in_pack_order() -> None:
    # spec: eval-008 -- the marker works down the pack, so the sheet must
    # too; a sheet in another order makes every row a lookup.
    pack = packed()
    rows = sheet_of(pack)

    ids = [rows.cell(row=n + 2, column=1).value for n in range(len(pack.items))]
    assert ids == [item.item_id for item in pack.items]


def test_the_workbook_and_the_csv_carry_the_same_rows() -> None:
    # spec: eval-008 -- one pass over one list. A workbook built from a
    # second traversal is a second place for the two to disagree, and the
    # disagreement would surface as `eval-006` ingesting rows nobody scored.
    pack = packed()
    rows = sheet_of(pack)

    from_sheet = [
        rows.cell(row=n + 2, column=1).value for n in range(len(pack.items))
    ]
    from_csv = [
        line.split(",")[0]
        for line in pack.score_sheet_csv.strip().splitlines()[1:]
    ]
    assert from_sheet == from_csv


def test_the_header_is_worded_as_the_rubric_words_it() -> None:
    # spec: eval-008 -- `overall_usefulness` is a field name. The scorer is
    # reading a handout that says "Overall usefulness".
    rows = sheet_of(packed())

    header = [cell.value for cell in rows[1]]
    assert "evidence_use" not in header
    assert any(h and "Evidence use" in h for h in header)


# ------------------------------------------------------- what it will accept


def test_the_five_dimensions_offer_only_the_rubrics_scale() -> None:
    # spec: eval-008 -- a sheet that accepts a 4 collects values the
    # pre-registered analysis has no anchor for, and the anchors are the
    # whole reason the scale is 1/3/5 rather than 1-5.
    rows = sheet_of(packed())
    header = {cell.value: cell.column for cell in rows[1]}

    for name in DIMENSIONS:
        column = header[ANCHORS[name]["heading"]]
        assert _validation_for(rows, column) == [str(n) for n in SCALE], name


def test_the_two_second_pass_judgements_offer_their_own_words() -> None:
    # spec: eval-008 -- pass two is categorical, not ordinal. A 1/3/5
    # dropdown on "cause correctness" would collect a number nothing in the
    # rubric maps back to a word.
    rows = sheet_of(packed())
    header = {cell.value: cell.column for cell in rows[1]}

    for name in JUDGEMENTS:
        column = header[ANCHORS[name]["heading"]]
        offered = _validation_for(rows, column)
        assert offered == list(ANCHORS[name]["options"]), name
        assert not any(word.isdigit() for word in offered)


def _validation_for(sheet, column: int) -> list[str]:
    """The list one column will accept, as the sheet stores it."""
    for validation in sheet.data_validations.dataValidation:
        if any(cells.min_col == column for cells in validation.sqref.ranges):
            return validation.formula1.strip('"').split(",")
    raise AssertionError(f"column {column} carries no validation at all")


def test_each_of_the_five_dimensions_is_validated() -> None:
    # spec: eval-008 -- five dropdowns, not four and a free-text column.
    rows = sheet_of(packed())

    validated = set()
    for v in rows.data_validations.dataValidation:
        for cells in v.sqref.ranges:
            validated.add(cells.min_col)
    header = {cell.column: cell.value for cell in rows[1]}
    scored = {col for col, name in header.items() if name in _headings()}
    assert scored <= validated, f"unvalidated scored columns: {scored - validated}"


def _headings() -> set[str]:
    return {ANCHORS[name]["heading"] for name in (*DIMENSIONS, *JUDGEMENTS)}


def test_a_dimension_with_no_anchor_is_refused() -> None:
    # spec: eval-008 -- exported with an empty dropdown it reads to the
    # scorer as a broken file and to a reader of the results as a dimension
    # nobody scored.
    pack = packed()

    with pytest.raises(ConfigurationError, match="anchor"):
        score_sheet_workbook(pack.items, dimensions=(*DIMENSIONS, "invented"))


def test_a_scale_the_rubric_does_not_use_is_refused() -> None:
    # spec: eval-008 -- the failure case stated on the item.
    pack = packed()

    with pytest.raises(ConfigurationError, match="scale"):
        score_sheet_workbook(pack.items, scale=(1, 2, 3, 4, 5))


# ------------------------------------------------------ what it gives back


def test_the_anchors_travel_with_the_sheet() -> None:
    # spec: eval-008 -- so the handout does not have to be open beside it.
    # A rater flipping between two documents forty times drifts.
    book = opened(score_sheet_workbook(packed().items))

    assert len(book.sheetnames) >= 2
    text = "\n".join(
        str(cell.value)
        for sheet in book
        for row in sheet.iter_rows()
        for cell in row
        if cell.value
    )
    for name in DIMENSIONS:
        for level in SCALE:
            assert ANCHORS[name][level] in text, f"{name} anchor {level} missing"


def test_the_identifier_columns_cannot_be_typed_over() -> None:
    # spec: eval-008 -- the one edit that silently destroys the join
    # `eval-006` makes between two raters' sheets and the key.
    rows = sheet_of(packed())

    assert rows.protection.sheet is True
    assert rows.cell(row=2, column=1).protection.locked is True
    scored = next(
        cell.column
        for cell in rows[1]
        if cell.value == ANCHORS[DIMENSIONS[0]]["heading"]
    )
    assert rows.cell(row=2, column=scored).protection.locked is False


def test_the_header_row_stays_on_screen() -> None:
    # spec: eval-008 -- forty rows of seven unlabelled columns otherwise.
    assert sheet_of(packed()).freeze_panes == "D2"


# ------------------------------------------------------------- the blinding


def test_no_part_of_the_marker_workbook_names_an_arm() -> None:
    # spec: eval-008, eval-004 -- the scan follows the artefact, or it simply
    # stops covering the place the leak would be.
    book = opened(score_sheet_workbook(packed().items))

    haystack = " ".join(
        [
            *book.sheetnames,
            *(str(book.properties.creator or "")),
            *(str(book.properties.title or "")),
        ]
        + [
            str(cell.value)
            for sheet in book
            for row in sheet.iter_rows()
            for cell in row
            if cell.value is not None
        ]
        + [
            str(cell.comment.text)
            for sheet in book
            for row in sheet.iter_rows()
            for cell in row
            if cell.comment is not None
        ]
    ).lower()

    for word in BLINDING_GIVEAWAYS:
        assert word not in haystack, f"{word!r} appears in the marker's workbook"


def test_the_key_is_its_own_workbook_and_not_a_tab() -> None:
    # spec: eval-008 -- a tab is one click from the sheet being scored in.
    pack = packed()
    marker = opened(score_sheet_workbook(pack.items))
    key = opened(arm_key_workbook(pack.items))

    assert not any("key" in name.lower() for name in marker.sheetnames)
    values = " ".join(
        str(cell.value)
        for row in key.active.iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert any(word in values for word in BLINDING_GIVEAWAYS)
    assert len(list(key.active.iter_rows())) == len(pack.items) + 1
