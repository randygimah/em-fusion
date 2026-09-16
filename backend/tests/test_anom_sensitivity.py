"""Track-gap detection sensitivity. Spec: anom-011.

Every rule above `anom-010` rests on an unchecked assumption: that when the
generator stages a disruption on an aircraft, the detector notices.
Measured 2026-09-15, it notices one in five. That number is why `anom-004`
cannot discriminate and why `anom-005` would report an interference zone on
seventy per cent of the runs whose truth is a sensor fault.

This item turns 21 per cent from a number into an account. A staged
aircraft can be lost at six places, and **three of them are the detector
being right** -- an aircraft on the ground was switched off, one at the
edge of the box flew out of view, a gap under the threshold is a gap under
the threshold. Until they are counted apart, the figure cannot say which.

Two constraints from the item drive most of what is asserted here. The
first is that attribution is **counted, not named**: a `Recall` whose
losses do not account for every undetected aircraft is refused at
construction, so the arithmetic cannot be skipped. The second is that a
figure without its conditions fails the spec, per this project's rule that
a measurement whose method is not recorded is a memory -- so `Conditions`
is mandatory and carries the policy the figure was taken under.

The most important test in the file is neither of those. It is
`test_the_diagnostic_path_agrees_with_the_detection_path`: the harness must
never reimplement a filter to work out which one fired, because two copies
of a rule that drift apart is a trap already recorded in this repository.
The diagnostic path shares the detection path's predicates, and that test
is what holds them together.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.dal.models import (
    CanonicalObservation,
    DataMode,
    Location,
    ObservationType,
    Provenance,
    SourceType,
    TrackPayload,
    ValidationStatus,
)
from app.detection.sensitivity import (
    Conditions,
    Loss,
    Recall,
    measure_recall,
)
from app.detection.track_gap import (
    BoundingBox,
    GapPolicy,
    Rejection,
    detect_track_gaps,
    explain_track_gaps,
)

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(
    threshold=timedelta(seconds=100),
    contact_fresh_within=timedelta(seconds=30),
    box=BOX,
)

INSIDE = Location(lat=52.0, lon=7.0)
#: Within the 0.25 degree interior margin of the box's northern edge.
EDGE = Location(lat=53.9, lon=7.0)

CONDITIONS = Conditions(
    batch="test-batch",
    scenario_type="gnss-degradation",
    runs=1,
    threshold_s=100.0,
    contact_fresh_within_s=30.0,
    interior_margin_deg=0.25,
)


def report(
    *,
    aircraft: str,
    at: float,
    location: Location = INSIDE,
    on_ground: bool = False,
    position_staleness_s: float = 1.0,
    contact_staleness_s: float = 0.0,
) -> CanonicalObservation:
    return CanonicalObservation(
        source_id="opensky-replay",
        source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK,
        timestamp=START + timedelta(seconds=at),
        location=location,
        data_mode=DataMode.REPLAYED,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="opensky-replay",
            source_type=SourceType.OPENSKY,
            data_mode=DataMode.REPLAYED,
            scenario_run_id=1,
        ),
        payload=TrackPayload(
            aircraft_id=aircraft,
            altitude_m=10000.0,
            velocity_ms=200.0,
            heading_deg=90.0,
            vertical_rate_ms=0.0,
            on_ground=on_ground,
            position_staleness_s=position_staleness_s,
            contact_staleness_s=contact_staleness_s,
        ),
    )


def reasons(verdicts, aircraft: str) -> set[Rejection]:
    (verdict,) = [v for v in verdicts if v.aircraft_id == aircraft]
    return set(verdict.rejections)


# ------------------------------------------------ the two paths must agree


def test_the_diagnostic_path_agrees_with_the_detection_path() -> None:
    """The anti-drift test, and the reason the harness has no filters of
    its own. A second copy of a rule written to explain the first is the
    trap this project recorded when a remedy lived in two places and the
    third caller knew about neither.
    """
    # spec: anom-011, anom-010
    observations = [
        # Detected: a long absence between two interior airborne reports.
        report(aircraft="found", at=0),
        report(aircraft="found", at=300),
        # Rejected: on the ground at one end.
        report(aircraft="grounded", at=0, on_ground=True),
        report(aircraft="grounded", at=300),
        # Rejected: the interval is under the threshold.
        report(aircraft="brief", at=0),
        report(aircraft="brief", at=50),
        # Rejected: nothing to bracket the absence.
        report(aircraft="solo", at=0),
    ]

    raised = {gap.aircraft_id for gap in detect_track_gaps(observations, POLICY)}
    explained = {v.aircraft_id for v in explain_track_gaps(observations, POLICY) if v.detected}

    assert raised == explained == {"found"}


def test_every_aircraft_gets_exactly_one_verdict() -> None:
    """Including one the rule raised nothing for. An aircraft missing from
    the verdicts would be silently outside the accounting."""
    # spec: anom-011
    observations = [
        report(aircraft="a", at=0),
        report(aircraft="a", at=300),
        report(aircraft="b", at=0),
    ]

    verdicts = explain_track_gaps(observations, POLICY)

    assert [v.aircraft_id for v in verdicts] == ["a", "b"]


def test_a_detected_aircraft_carries_no_rejection() -> None:
    # spec: anom-011
    observations = [report(aircraft="a", at=0), report(aircraft="a", at=300)]

    (verdict,) = explain_track_gaps(observations, POLICY)

    assert verdict.detected
    assert verdict.rejections == ()


# ------------------------------------------------------- each loss, counted


def test_an_aircraft_on_the_ground_is_rejected_as_such() -> None:
    """Correct behaviour, not a miss: it stopped reporting because it was
    switched off."""
    # spec: anom-011, anom-010
    observations = [
        report(aircraft="parked", at=0, on_ground=True),
        report(aircraft="parked", at=300),
    ]

    assert Rejection.ON_GROUND in reasons(explain_track_gaps(observations, POLICY), "parked")


def test_an_aircraft_at_the_edge_of_the_box_is_rejected_as_such() -> None:
    """Also correct: it flew out of view rather than went missing."""
    # spec: anom-011, anom-010
    observations = [
        report(aircraft="leaving", at=0, location=EDGE),
        report(aircraft="leaving", at=300, location=EDGE),
    ]

    assert Rejection.NOT_INTERIOR in reasons(
        explain_track_gaps(observations, POLICY), "leaving"
    )


def test_a_gap_under_the_threshold_is_rejected_as_such() -> None:
    # spec: anom-011
    observations = [report(aircraft="brief", at=0), report(aircraft="brief", at=50)]

    assert Rejection.BELOW_THRESHOLD in reasons(
        explain_track_gaps(observations, POLICY), "brief"
    )


def test_an_unbracketed_absence_is_rejected_as_such() -> None:
    """The expensive one. `anom-010` refuses to extrapolate a gap from a
    track's final report, because every aircraft still flying is stale when
    the window closes -- and the coverage-gap scenario stages by suppressing
    rows, which can remove the very report that would have closed the gap.
    Counting this separately is what will show how much that costs.
    """
    # spec: anom-011, anom-010, scn-002
    observations = [report(aircraft="solo", at=0)]

    assert Rejection.NO_PAIR in reasons(explain_track_gaps(observations, POLICY), "solo")


def test_a_stale_position_without_fresh_contact_is_rejected_as_such() -> None:
    """The two-clock discriminator refusing. Whether this is the generator
    not keeping contact fresh or the rule asking too much is exactly what
    the count is for."""
    # spec: anom-011, anom-010, dal-001
    observations = [
        report(aircraft="lost", at=0, position_staleness_s=200.0, contact_staleness_s=90.0),
        report(aircraft="lost", at=10, position_staleness_s=210.0, contact_staleness_s=100.0),
    ]

    assert Rejection.CONTACT_NOT_FRESH in reasons(
        explain_track_gaps(observations, POLICY), "lost"
    )


# ------------------------------------------------------------------ recall


def test_recall_is_measured_against_the_answer_key() -> None:
    """Against ground truth, never against the detector's own output. A
    staged aircraft the detector never emitted anything for is a miss, not
    an absence from the denominator."""
    # spec: anom-011, scn-002
    observations = [
        report(aircraft="hit", at=0),
        report(aircraft="hit", at=300),
        report(aircraft="miss", at=0),
        report(aircraft="miss", at=50),
    ]

    result = measure_recall(
        staged_aircraft={"hit", "miss"},
        observations=observations,
        policy=POLICY,
        conditions=CONDITIONS,
    )

    assert result.staged == 2
    assert result.detected == 1
    assert result.rate == pytest.approx(0.5)


def test_a_staged_aircraft_absent_from_the_run_is_a_loss_not_an_omission() -> None:
    """The generator targeted it and it never appeared. That is a real
    failure with a different cause from every other entry here, and
    dropping it from the denominator would flatter the figure."""
    # spec: anom-011, scn-002
    observations = [report(aircraft="present", at=0), report(aircraft="present", at=300)]

    result = measure_recall(
        staged_aircraft={"present", "ghost"},
        observations=observations,
        policy=POLICY,
        conditions=CONDITIONS,
    )

    assert result.staged == 2
    assert result.detected == 1
    assert result.losses[Loss.NOT_IN_RUN] == 1


def test_the_losses_account_for_every_undetected_aircraft() -> None:
    """The item forbids attributing a loss without counting it. Enforced by
    arithmetic rather than by review: a tally that does not add up is
    refused at construction."""
    # spec: anom-011
    observations = [
        report(aircraft="hit", at=0),
        report(aircraft="hit", at=300),
        report(aircraft="grounded", at=0, on_ground=True),
        report(aircraft="grounded", at=300),
        report(aircraft="brief", at=0),
        report(aircraft="brief", at=50),
    ]

    result = measure_recall(
        staged_aircraft={"hit", "grounded", "brief", "ghost"},
        observations=observations,
        policy=POLICY,
        conditions=CONDITIONS,
    )

    assert sum(result.losses.values()) == result.staged - result.detected == 3


def test_a_tally_that_does_not_add_up_is_refused() -> None:
    # spec: anom-011
    with pytest.raises(ValueError, match="account"):
        Recall(
            conditions=CONDITIONS,
            staged=10,
            detected=2,
            losses={Loss.ON_GROUND: 3},
        )


def test_a_recall_figure_carries_the_conditions_it_was_taken_under() -> None:
    """A measurement whose method is not recorded is a memory. The project
    has been caught by that once already, with a timing figure taken by a
    script that no longer existed and recorded differently in three
    documents."""
    # spec: anom-011, NFR-601
    result = measure_recall(
        staged_aircraft={"hit"},
        observations=[report(aircraft="hit", at=0), report(aircraft="hit", at=300)],
        policy=POLICY,
        conditions=CONDITIONS,
    )

    assert result.conditions.threshold_s == 100.0
    assert result.conditions.contact_fresh_within_s == 30.0
    assert result.conditions.batch == "test-batch"
    assert result.conditions.scenario_type == "gnss-degradation"


def test_a_recall_cannot_be_built_without_conditions() -> None:
    # spec: anom-011
    with pytest.raises(TypeError):
        Recall(staged=1, detected=1, losses={})  # type: ignore[call-arg]


def test_a_run_that_staged_nothing_is_refused_rather_than_scored() -> None:
    """One seed in the stored batch staged zero aircraft across all three
    of its runs. Scoring it as nought per cent would drag an average down
    for a reason that has nothing to do with the detector, and scoring it
    as a hundred would do the reverse. It has to be excluded deliberately.
    """
    # spec: anom-011, eval-002
    with pytest.raises(ValueError, match="staged nothing"):
        measure_recall(
            staged_aircraft=set(),
            observations=[report(aircraft="a", at=0)],
            policy=POLICY,
            conditions=CONDITIONS,
        )


def test_the_conditions_are_derived_from_the_policy_not_retyped() -> None:
    """A figure whose recorded conditions could disagree with the policy it
    was actually measured under is worse than one with no conditions at
    all."""
    # spec: anom-011
    policy = GapPolicy(
        threshold=timedelta(seconds=250),
        contact_fresh_within=timedelta(seconds=45),
        box=BOX,
    )

    result = measure_recall(
        staged_aircraft={"hit"},
        observations=[report(aircraft="hit", at=0), report(aircraft="hit", at=400)],
        policy=policy,
        conditions=Conditions(batch="b", scenario_type="s", runs=1),
    )

    assert result.conditions.threshold_s == 250.0
    assert result.conditions.contact_fresh_within_s == 45.0


def test_recall_is_deterministic(
) -> None:
    # spec: anom-011, NFR-601
    observations = [
        report(aircraft="hit", at=0),
        report(aircraft="hit", at=300),
        report(aircraft="brief", at=0),
        report(aircraft="brief", at=50),
    ]
    staged = {"hit", "brief"}

    first = measure_recall(
        staged_aircraft=staged, observations=observations, policy=POLICY,
        conditions=CONDITIONS,
    )
    second = measure_recall(
        staged_aircraft=staged, observations=list(reversed(observations)), policy=POLICY,
        conditions=CONDITIONS,
    )

    assert first == second
