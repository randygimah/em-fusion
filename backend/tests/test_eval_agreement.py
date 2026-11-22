"""Blind-score ingest and inter-rater agreement. Spec: eval-006.

Pure functions over bytes and mappings: no database, no model. The sheets
here are built in the test with the same headings the marker's workbook
carries (`eval-008`), so the join under test is the one the real sheets
make: on the item id, never on row order.
"""

from __future__ import annotations

import inspect
import io

import pytest
from openpyxl import Workbook

from app.evaluation.agreement import (
    FLAG_GAP,
    KAPPA_RESAMPLES,
    KAPPA_SEED,
    AgreementError,
    agreement,
    arm_summary,
    flagged,
    pack_interval,
    quadratic_weighted_kappa,
    read_arm_key,
    read_score_sheet,
)
from app.evaluation.pack import DIMENSIONS, JUDGEMENTS
from app.evaluation.workbook import ANCHORS, IDENTIFIERS, SHEET

# --- helpers ----------------------------------------------------------------


def _sheet(rows: list[tuple], *, header: list[str] | None = None) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    sheet.append(
        header
        or [*IDENTIFIERS, *(ANCHORS[n]["heading"] for n in (*DIMENSIONS, *JUDGEMENTS))]
    )
    for row in rows:
        sheet.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _row(
    item: str,
    scores: tuple[int, ...] = (3, 3, 3, 3, 3),
    cause="Correct",
    cal="About right",
):
    pack, label = item.split("-")
    return (item, pack, label, *scores, cause, cal)


def _rows(spec: dict[str, tuple[int, ...]]):
    return read_score_sheet(_sheet([_row(item, s) for item, s in spec.items()]))


# --- the statistic ----------------------------------------------------------


def test_identical_ratings_agree_perfectly() -> None:
    assert quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(
        1.0
    )


def test_a_reversed_scale_is_perfect_disagreement() -> None:
    # Observed mean squared gap 8 against 4 expected by chance: 1 - 8/4.
    assert quadratic_weighted_kappa([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(
        -1.0
    )


def test_a_worked_value_with_unequal_marginals() -> None:
    # Observed 0.25; expected 0.5 * 0.75 + 0.5 * 0.25 = 0.5; kappa 0.5.
    assert quadratic_weighted_kappa([1, 1, 2, 2], [1, 2, 2, 2]) == pytest.approx(0.5)


def test_weighting_is_quadratic_not_linear_or_none() -> None:
    # A 1-vs-3 miss must cost four times a 1-vs-2 miss. Linear weights give a
    # different value here, unweighted kappa a third.
    a = [1, 1, 3, 3, 5, 5]
    b = [1, 3, 3, 5, 5, 1]
    observed = (0 + 4 + 0 + 4 + 0 + 16) / 6
    pa = {1: 2 / 6, 3: 2 / 6, 5: 2 / 6}
    pb = {1: 2 / 6, 3: 2 / 6, 5: 2 / 6}
    expected = sum(pa[i] * pb[j] * (i - j) ** 2 for i in pa for j in pb)
    assert quadratic_weighted_kappa(a, b) == pytest.approx(1 - observed / expected)


def test_no_variation_at_all_is_undefined_not_perfect() -> None:
    assert quadratic_weighted_kappa([3, 3, 3], [3, 3, 3]) is None


def test_one_constant_rater_is_zero_not_undefined() -> None:
    assert quadratic_weighted_kappa([3, 3], [3, 4]) == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("a", "b"),
    [([], []), ([1, 2], [1]), ([0, 3], [1, 3]), ([1, 6], [1, 3])],
)
def test_the_statistic_refuses_what_it_cannot_score(a, b) -> None:
    with pytest.raises(AgreementError):
        quadratic_weighted_kappa(a, b)


# --- reading a sheet --------------------------------------------------------


def test_a_sheet_is_read_by_heading_into_field_names() -> None:
    (row,) = read_score_sheet(
        _sheet([_row("00248-A", (1, 2, 3, 4, 5), "Partly correct", "Too low")])
    )
    assert row.item_id == "00248-A"
    assert row.bundle_id == 248
    assert row.label == "A"
    assert dict(row.scores) == dict(zip(DIMENSIONS, (1, 2, 3, 4, 5)))
    assert dict(row.judgements) == {
        "cause_correctness": "Partly correct",
        "confidence_calibration": "Too low",
    }


def test_a_dropdown_value_stored_as_text_is_read_as_its_number() -> None:
    (row,) = read_score_sheet(
        _sheet(
            [
                (
                    "00248-A",
                    "00248",
                    "A",
                    "4",
                    "4",
                    "4",
                    "4",
                    "4",
                    "Correct",
                    "About right",
                )
            ]
        )
    )
    assert set(row.scores.values()) == {4}


def test_a_blank_score_is_refused_not_skipped() -> None:
    with pytest.raises(AgreementError, match="00248-A"):
        read_score_sheet(
            _sheet(
                [("00248-A", "00248", "A", 4, None, 4, 4, 4, "Correct", "About right")]
            )
        )


def test_a_score_off_the_scale_is_refused() -> None:
    with pytest.raises(AgreementError):
        read_score_sheet(_sheet([_row("00248-A", (4, 4, 6, 4, 4))]))


def test_an_unknown_judgement_is_refused() -> None:
    with pytest.raises(AgreementError):
        read_score_sheet(_sheet([_row("00248-A", cause="Mostly")]))


def test_a_repeated_item_is_refused() -> None:
    with pytest.raises(AgreementError, match="00248-A"):
        read_score_sheet(_sheet([_row("00248-A"), _row("00248-A")]))


def test_an_item_whose_id_disagrees_with_its_pack_or_label_is_refused() -> None:
    with pytest.raises(AgreementError):
        read_score_sheet(
            _sheet([("00248-A", "00250", "A", 3, 3, 3, 3, 3, "Correct", "About right")])
        )


def test_a_sheet_with_a_missing_heading_is_refused() -> None:
    header = [*IDENTIFIERS, *(ANCHORS[n]["heading"] for n in DIMENSIONS)]
    with pytest.raises(AgreementError):
        read_score_sheet(_sheet([], header=header))


# --- agreement over the double-scored items ---------------------------------


def test_kappa_is_computed_over_items_both_raters_scored_joined_on_id() -> None:
    first = _rows(
        {
            "00001-A": (1,) * 5,
            "00001-B": (5,) * 5,
            "00002-A": (1,) * 5,
            "00002-B": (5,) * 5,
        }
    )
    # Second rater: different row order, and only pack 00001.
    second = _rows({"00001-B": (5,) * 5, "00001-A": (1,) * 5})
    result = agreement(first, second)
    assert result.double_scored == ("00001-A", "00001-B")
    assert result.single_rated == ("00002-A", "00002-B")
    for dimension in DIMENSIONS:
        assert result.dimensions[dimension].n == 2
        assert result.dimensions[dimension].kappa == pytest.approx(1.0)


def test_an_item_only_the_second_rater_scored_is_refused() -> None:
    first = _rows({"00001-A": (3,) * 5})
    second = _rows({"00001-A": (3,) * 5, "00009-A": (3,) * 5})
    with pytest.raises(AgreementError, match="00009-A"):
        agreement(first, second)


def test_agreement_cannot_be_given_the_arm_key() -> None:
    # The key is joined only after both sheets are in; the agreement step has
    # no parameter through which it could arrive.
    assert set(inspect.signature(agreement).parameters) == {"first", "second"}


def test_exact_and_within_one_counts_are_reported() -> None:
    first = _rows({"00001-A": (3, 3, 3, 3, 3), "00001-B": (2, 2, 2, 2, 2)})
    second = _rows({"00001-A": (3, 4, 5, 3, 3), "00001-B": (2, 2, 2, 2, 2)})
    result = agreement(first, second)
    assert (
        result.dimensions["evidence_use"].exact,
        result.dimensions["evidence_use"].within_one,
    ) == (2, 2)
    assert (
        result.dimensions["uncertainty"].exact,
        result.dimensions["uncertainty"].within_one,
    ) == (1, 2)
    assert (
        result.dimensions["alternatives"].exact,
        result.dimensions["alternatives"].within_one,
    ) == (1, 1)


def test_a_gap_of_two_or_more_is_flagged_for_discussion() -> None:
    assert FLAG_GAP == 2
    first = _rows({"00001-A": (3, 3, 3, 3, 3)})
    second = _rows({"00001-A": (4, 5, 1, 3, 3)})
    flags = flagged(first, second)
    assert [(f.item_id, f.dimension, f.first, f.second) for f in flags] == [
        ("00001-A", "uncertainty", 3, 5),
        ("00001-A", "alternatives", 3, 1),
    ]


# --- the interval -----------------------------------------------------------


def test_the_interval_seed_and_resamples_are_declared() -> None:
    assert isinstance(KAPPA_SEED, int)
    assert KAPPA_RESAMPLES >= 1000


def _paired(n_packs: int, gap: int = 0):
    first, second = {}, {}
    for pack in range(1, n_packs + 1):
        for label, base in (("A", 1 + pack % 4), ("B", 2 + pack % 3)):
            item = f"{pack:05d}-{label}"
            first[item] = (base,) * 5
            second[item] = (min(5, base + gap),) * 5
    return _rows(first), _rows(second)


def test_the_interval_resamples_whole_packs_and_is_reproducible() -> None:
    first, second = _paired(10, gap=0)
    once = pack_interval(first, second, "evidence_use", resamples=500)
    again = pack_interval(first, second, "evidence_use", resamples=500)
    assert once == again
    assert once.low == pytest.approx(1.0) and once.high == pytest.approx(1.0)


def test_the_interval_brackets_the_point_estimate() -> None:
    first, second = _paired(10, gap=1)
    point = agreement(first, second).dimensions["evidence_use"].kappa
    interval = pack_interval(first, second, "evidence_use", resamples=500)
    assert interval.low <= point <= interval.high
    assert interval.resamples + interval.undefined == 500


# --- per arm, once both sheets are in ---------------------------------------


def _key(*packs: str) -> dict[str, str]:
    key = {}
    for pack in packs:
        key[f"{pack}-A"] = "template"
        key[f"{pack}-B"] = "hosted"
    return key


def test_read_arm_key_accepts_the_committed_csv_shape() -> None:
    text = "item_id,bundle_id,label,arm\n00248-A,248,A,template\n00248-B,248,B,hosted\n"
    assert read_arm_key(text) == {"00248-A": "template", "00248-B": "hosted"}


def test_an_arm_key_with_two_items_of_one_arm_in_a_pack_is_refused() -> None:
    text = "item_id,bundle_id,label,arm\n00248-A,248,A,hosted\n00248-B,248,B,hosted\n"
    with pytest.raises(AgreementError):
        read_arm_key(text)


def test_double_scored_means_average_the_two_raters_and_differences_are_paired() -> (
    None
):
    first = _rows(
        {
            "00001-A": (2,) * 5,
            "00001-B": (4,) * 5,
            "00002-A": (1,) * 5,
            "00002-B": (5,) * 5,
        }
    )
    second = _rows({"00001-A": (2,) * 5, "00001-B": (5,) * 5})
    summary = arm_summary(first, second, _key("00001", "00002"))
    double = summary.double_scored["evidence_use"]
    assert double.template.mean == pytest.approx(2.0)
    assert double.hosted.mean == pytest.approx(4.5)
    assert double.difference == pytest.approx(2.5)
    assert double.hosted.n == double.template.n == 1


def test_first_rater_corpus_is_apart_and_never_averaged_with_a_missing_score() -> None:
    first = _rows(
        {
            "00001-A": (2,) * 5,
            "00001-B": (4,) * 5,
            "00002-A": (1,) * 5,
            "00002-B": (5,) * 5,
        }
    )
    second = _rows({"00001-A": (2,) * 5, "00001-B": (5,) * 5})
    summary = arm_summary(first, second, _key("00001", "00002"))
    single = summary.first_rater["evidence_use"]
    assert single.hosted.mean == pytest.approx(4.5)  # (4 + 5) / 2, first rater only
    assert single.template.mean == pytest.approx(1.5)
    assert single.hosted.n == 2


def test_distributions_count_every_point_of_the_scale() -> None:
    first = _rows({"00001-A": (2,) * 5, "00001-B": (4,) * 5})
    second = _rows({"00001-A": (2,) * 5, "00001-B": (4,) * 5})
    summary = arm_summary(first, second, _key("00001"))
    assert summary.first_rater["evidence_use"].hosted.distribution == {
        1: 0,
        2: 0,
        3: 0,
        4: 1,
        5: 0,
    }


def test_pass_two_judgements_are_counts_per_arm_per_rater() -> None:
    first = read_score_sheet(
        _sheet([_row("00001-A", cause="Incorrect"), _row("00001-B")])
    )
    second = read_score_sheet(
        _sheet([_row("00001-A"), _row("00001-B", cal="Too high")])
    )
    summary = arm_summary(first, second, _key("00001"))
    assert summary.judgements["first"]["template"]["cause_correctness"] == {
        "Correct": 0,
        "Partly correct": 0,
        "Incorrect": 1,
    }
    assert (
        summary.judgements["second"]["hosted"]["confidence_calibration"]["Too high"]
        == 1
    )


def test_an_arm_key_missing_a_scored_item_is_refused() -> None:
    first = _rows(
        {
            "00001-A": (3,) * 5,
            "00001-B": (3,) * 5,
            "00002-A": (3,) * 5,
            "00002-B": (3,) * 5,
        }
    )
    second = _rows({"00001-A": (3,) * 5, "00001-B": (3,) * 5})
    with pytest.raises(AgreementError, match="00002"):
        arm_summary(first, second, _key("00001"))


def test_an_averaged_score_is_counted_on_the_half_point_it_falls_on() -> None:
    # Two raters averaged can give 4.5; a distribution over 1-5 alone would
    # drop it and report fewer items than were scored.
    first = _rows({"00001-A": (2,) * 5, "00001-B": (4,) * 5})
    second = _rows({"00001-A": (2,) * 5, "00001-B": (5,) * 5})
    hosted = (
        arm_summary(first, second, _key("00001")).double_scored["evidence_use"].hosted
    )
    assert hosted.distribution[4.5] == 1
    assert sum(hosted.distribution.values()) == hosted.n
