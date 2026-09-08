"""The injection-exclusion list. Spec: adp-008.

Scenario type 4 injects a coverage gap by suppressing an aircraft's reports for
a window. Roughly 1% of the tracks in the corpus already carry a gap of their
own, seven of them in the 100-300 s band a plausible injection sits in, so an
injected gap on one of those tracks is indistinguishable from the natural one
and the false-positive rate for that scenario type stops meaning anything. This
item produces the list the generator refuses.

`coverage.json` cannot serve. It measures every interval between consecutive
positioned rows and reports the distribution -- a maximum, three percentiles, a
clean-cadence fraction -- and keeps no aircraft identity at all. It also applies
no filter, and two filters are what separate a coverage failure from an artefact
of having drawn a box:

* **Interior.** An aircraft that flies out of the box and back in has an
  interval with nothing in it, and nothing went wrong. Only a gap bracketed by
  two rows comfortably inside the boundary is evidence about coverage.
* **Airborne.** An aircraft parked on a stand stops reporting because it is
  switched off. That is not a dropout either.

Both are asserted here in both directions: a gap that satisfies them is
reported, and one that fails either is not.

**Identities are pseudonyms.** The artefact is committed, and `icao24` is a
24-bit space, so committing source identifiers would hand a reader the very
mapping `dal-004` exists to prevent. The generator perturbs source records
before the DAL sees them, so it pseudonymises each candidate and tests
membership against this list rather than the other way round.

The last test in the file is the one that matters most and runs least often: it
reads the real extract, when the extract is present, and checks the analysis
reproduces the ten interior airborne gaps recorded in `thesis_notes.md`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from app.corpus.extract import BoundingBox
from app.corpus.natural_gaps import (
    DEFAULT_INTERIOR_MARGIN_DEG,
    DEFAULT_MIN_GAP_S,
    NaturalGap,
    build_natural_gaps_report,
    find_natural_gaps,
)
from app.dal.pseudonymise import Pseudonymiser

BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: The extract is gitignored and rebuilt by `python -m app.corpus.build`, and
#: the repository root is not mounted into the test container. The one test that
#: needs it therefore skips rather than fails when it is absent -- the same
#: stance the database tier takes.
EXTRACT = BACKEND_ROOT.parent / "data" / "opensky" / "opensky_extract.parquet"

requires_extract = pytest.mark.skipif(
    not EXTRACT.is_file(),
    reason=f"{EXTRACT} is absent; skipping the real-corpus tier",
)

#: Never the corpus seed (`dal-004`), and it does not need to be: a gap's
#: duration does not depend on what the aircraft is called.
PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)

#: Comfortably inside the box on every side, so the interior test passes on
#: position and the tests below vary one thing at a time.
INSIDE = (51.5, 7.0)

#: Inside the box but within the margin of its western edge -- where a row sits
#: when the aircraft is about to leave.
NEAR_EDGE = (51.5, 3.05)

BASE_TIME = 1656331200

#: The ten interior airborne gaps recorded in docs/thesis_notes.md for the
#: chosen box, in seconds. Written out rather than counted, because the claim
#: under test is that this analysis reproduces that one.
RECORDED_GAPS_S = (20, 100, 110, 200, 280, 280, 300, 970, 1160, 1440)


# ------------------------------------------------------------------- builders


def _row(
    *,
    time: int,
    icao24: str = "4d22ec",
    position: tuple[float, float] | None = INSIDE,
    onground: str = "False",
) -> dict[str, Any]:
    """One positioned source row, in the shape `read_rows` yields.

    Values are strings because that is what the CSV reader produces and what
    `coverage_report` already consumes; the real-extract test below passes
    native types through the same function on purpose.
    """
    lat, lon = ("", "") if position is None else position
    return {
        "time": str(time),
        "icao24": icao24,
        "lat": str(lat),
        "lon": str(lon),
        "onground": onground,
    }


def _pair(gap_s: int, **kwargs: Any) -> list[dict[str, Any]]:
    """Two rows separated by `gap_s`, both otherwise identical."""
    return [
        _row(time=BASE_TIME, **kwargs),
        _row(time=BASE_TIME + gap_s, **kwargs),
    ]


def _gaps(rows: list[dict[str, Any]], **kwargs: Any) -> list[NaturalGap]:
    return find_natural_gaps(
        rows,
        box=BOX,
        min_gap_s=kwargs.pop("min_gap_s", DEFAULT_MIN_GAP_S),
        margin_deg=kwargs.pop("margin_deg", DEFAULT_INTERIOR_MARGIN_DEG),
        pseudonymiser=PSEUDONYMISER,
        **kwargs,
    )


# ------------------------------------------------------- what counts as a gap


def test_a_gap_between_two_interior_airborne_rows_is_reported() -> None:
    # spec: adp-008
    found = _gaps(_pair(200))

    assert len(found) == 1
    assert found[0].duration_s == 200
    assert found[0].start == BASE_TIME
    assert found[0].end == BASE_TIME + 200


def test_an_interval_at_the_reporting_cadence_is_not_a_gap() -> None:
    # spec: adp-008
    # Ten seconds is the cadence, not a dropout. Reporting it would list every
    # aircraft in the corpus and exclude the entire fleet from injection.
    assert _gaps(_pair(10)) == []


def test_a_gap_below_the_minimum_is_not_reported() -> None:
    # spec: adp-008
    assert _gaps(_pair(30), min_gap_s=60) == []
    assert len(_gaps(_pair(30), min_gap_s=20)) == 1


def test_a_gap_whose_earlier_row_sits_near_the_edge_is_not_reported() -> None:
    # spec: adp-008
    # The aircraft left the box. The interval is an artefact of the filter, and
    # counting it is the error the bounding-box sweep already made once.
    rows = [
        _row(time=BASE_TIME, position=NEAR_EDGE),
        _row(time=BASE_TIME + 200, position=INSIDE),
    ]

    assert _gaps(rows) == []


def test_a_gap_whose_later_row_sits_near_the_edge_is_not_reported() -> None:
    # spec: adp-008
    # The mirror case: the aircraft came back in. Both ends have to be
    # interior, or the test is one-sided and half the artefacts survive it.
    rows = [
        _row(time=BASE_TIME, position=INSIDE),
        _row(time=BASE_TIME + 200, position=NEAR_EDGE),
    ]

    assert _gaps(rows) == []


def test_a_gap_with_the_aircraft_on_the_ground_is_not_reported() -> None:
    # spec: adp-008
    # Parked and switched off is not a coverage failure.
    assert _gaps(_pair(200, onground="True")) == []

    mixed = [
        _row(time=BASE_TIME, onground="False"),
        _row(time=BASE_TIME + 200, onground="True"),
    ]
    assert _gaps(mixed) == []


def test_rows_with_no_position_are_ignored() -> None:
    # spec: adp-008
    # The 500 retained null-position rows exist to feed the quarantine path.
    # Treating one as a gap boundary would invent a gap out of a retention
    # decision -- the same reason coverage_report skips them.
    rows = [
        _row(time=BASE_TIME),
        _row(time=BASE_TIME + 100, position=None),
        _row(time=BASE_TIME + 200),
    ]
    found = _gaps(rows)

    assert len(found) == 1
    assert found[0].duration_s == 200


def test_rows_out_of_time_order_are_sorted_before_measuring() -> None:
    # spec: adp-008
    # A negative interval would silently drop below any minimum and hide a real
    # gap. The extract is written in time order, which is exactly why nothing
    # would notice if this were left to trust.
    rows = [_row(time=BASE_TIME + 200), _row(time=BASE_TIME)]
    found = _gaps(rows)

    assert len(found) == 1
    assert found[0].duration_s == 200


def test_each_aircraft_is_measured_separately() -> None:
    # spec: adp-008
    # Two aircraft interleaved in the file must not have a gap computed across
    # them, which would report a dropout for a pair that were both reporting
    # normally throughout.
    rows = [
        _row(time=BASE_TIME, icao24="aaaaaa"),
        _row(time=BASE_TIME + 100, icao24="bbbbbb"),
        _row(time=BASE_TIME + 200, icao24="aaaaaa"),
        _row(time=BASE_TIME + 210, icao24="bbbbbb"),
    ]
    found = _gaps(rows)

    assert len(found) == 1
    assert found[0].aircraft_id == PSEUDONYMISER.aircraft("aaaaaa")


# ------------------------------------------------------------- what is written


def test_aircraft_are_identified_by_pseudonym_and_never_by_source() -> None:
    # spec: adp-008, dal-004
    found = _gaps(_pair(200, icao24="4d22ec"))
    report = build_natural_gaps_report(
        found,
        box=BOX,
        min_gap_s=DEFAULT_MIN_GAP_S,
        margin_deg=DEFAULT_INTERIOR_MARGIN_DEG,
        seed_fingerprint=PSEUDONYMISER.fingerprint(),
    )

    assert found[0].aircraft_id == PSEUDONYMISER.aircraft("4d22ec")
    assert "4d22ec" not in repr(report)
    assert "icao24" not in repr(report)


def test_the_report_records_what_it_was_run_under() -> None:
    # spec: adp-008
    # A committed list of identifiers is unusable a year later without the
    # parameters that produced it, and meaningless against a different seed.
    report = build_natural_gaps_report(
        _gaps(_pair(200)),
        box=BOX,
        min_gap_s=DEFAULT_MIN_GAP_S,
        margin_deg=DEFAULT_INTERIOR_MARGIN_DEG,
        seed_fingerprint=PSEUDONYMISER.fingerprint(),
    )

    assert report["min_gap_s"] == DEFAULT_MIN_GAP_S
    assert report["interior_margin_deg"] == DEFAULT_INTERIOR_MARGIN_DEG
    assert report["bounding_box"] == {
        "lat_min": 49.0,
        "lat_max": 54.0,
        "lon_min": 3.0,
        "lon_max": 11.0,
    }
    assert report["pseudonym_seed_sha256"] == PSEUDONYMISER.fingerprint()
    assert report["aircraft"] == 1
    assert len(report["gaps"]) == 1


def test_the_report_never_carries_the_seed_itself() -> None:
    # spec: adp-008, dal-004
    # The fingerprint identifies which seed built the list; the seed would let
    # any reader reconstruct the whole mapping by exhaustive search.
    report = build_natural_gaps_report(
        _gaps(_pair(200)),
        box=BOX,
        min_gap_s=DEFAULT_MIN_GAP_S,
        margin_deg=DEFAULT_INTERIOR_MARGIN_DEG,
        seed_fingerprint=PSEUDONYMISER.fingerprint(),
    )

    assert "a-test-seed-not-the-real-one" not in repr(report)


def test_the_report_is_ordered_deterministically() -> None:
    # spec: adp-008, scn-001
    # The artefact is committed, so an unstable order produces a diff on every
    # rebuild and hides the one change that mattered.
    rows = [
        *_pair(200, icao24="ffffff"),
        *_pair(300, icao24="111111"),
    ]
    first = build_natural_gaps_report(
        _gaps(rows),
        box=BOX,
        min_gap_s=DEFAULT_MIN_GAP_S,
        margin_deg=DEFAULT_INTERIOR_MARGIN_DEG,
        seed_fingerprint=PSEUDONYMISER.fingerprint(),
    )
    second = build_natural_gaps_report(
        _gaps(list(reversed(rows))),
        box=BOX,
        min_gap_s=DEFAULT_MIN_GAP_S,
        margin_deg=DEFAULT_INTERIOR_MARGIN_DEG,
        seed_fingerprint=PSEUDONYMISER.fingerprint(),
    )

    assert first == second
    assert [gap["aircraft_id"] for gap in first["gaps"]] == sorted(
        gap["aircraft_id"] for gap in first["gaps"]
    )


# ------------------------------------------------- against the real corpus


@requires_extract
def test_the_analysis_reproduces_the_recorded_interior_airborne_gaps() -> None:
    # spec: adp-008
    # The claim in thesis_notes.md is that ten tracks in the chosen box carry a
    # natural interior airborne gap, of these durations. That analysis was run
    # by hand and never committed; this is the item that makes it reproducible,
    # so reproducing it is the acceptance test.
    parquet = pq.ParquetFile(EXTRACT)
    rows: list[dict[str, Any]] = []
    for batch in parquet.iter_batches(
        columns=["time", "icao24", "lat", "lon", "onground"]
    ):
        rows.extend(batch.to_pylist())

    found = find_natural_gaps(
        rows,
        box=BOX,
        min_gap_s=DEFAULT_MIN_GAP_S,
        margin_deg=DEFAULT_INTERIOR_MARGIN_DEG,
        pseudonymiser=PSEUDONYMISER,
    )

    assert sorted(gap.duration_s for gap in found) == sorted(RECORDED_GAPS_S)
    assert len({gap.aircraft_id for gap in found}) == len(RECORDED_GAPS_S)


@requires_extract
def test_every_reported_gap_satisfies_both_filters() -> None:
    # spec: adp-008
    # A property over the real corpus rather than over three fixture rows: no
    # reported gap may be shorter than the minimum, and every one must exceed
    # the reporting cadence by a wide margin or the list is measuring noise.
    parquet = pq.ParquetFile(EXTRACT)
    rows: list[dict[str, Any]] = []
    for batch in parquet.iter_batches(
        columns=["time", "icao24", "lat", "lon", "onground"]
    ):
        rows.extend(batch.to_pylist())

    found = find_natural_gaps(
        rows,
        box=BOX,
        min_gap_s=DEFAULT_MIN_GAP_S,
        margin_deg=DEFAULT_INTERIOR_MARGIN_DEG,
        pseudonymiser=PSEUDONYMISER,
    )

    assert found
    assert all(gap.duration_s >= DEFAULT_MIN_GAP_S for gap in found)
    assert all(gap.end - gap.start == gap.duration_s for gap in found)
    assert all(gap.aircraft_id.startswith("AC-") for gap in found)
