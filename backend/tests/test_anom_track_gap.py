"""The track continuity rule, `TRACK-GAP`. Spec: anom-010.

The aircraft side of detection, and the rule the fusion pair rests on --
`anom-004` clusters what this produces and `anom-006` discriminates on it.

**Its output is an intermediate finding, not a reportable anomaly**, and
the tests are written in those terms because the measurement forced it. A
quiet run genuinely contains around 138 aircraft whose reported position
staleness exceeds 100 s, out of roughly 530 seen. Those are properties of
real replayed data. A rule emitting none of them would not be a quiet
detector, it would be a broken one, which is why `anom-008` was amended
alongside this item rather than this item being tuned to satisfy it.

Two mechanisms, because the two scenario types stage differently and a
rule with one of them is blind to the other. `gnss-degradation` rewrites
the reported staleness and the rows keep coming; `aircraft-coverage-gap`
suppresses the rows, so there is no field left to read. The first is
`frozen_position`, the second `not_heard`, and the shape travels on the
finding because telling those apart is exactly what the fusion rules do.

The two filters below are not fussiness. Measured on the twenty quiet
runs: 164 intervals exceed 100 s, 32 survive the airborne filter, and 23
survive the interior one. Without both, four fifths of what this rule
reported would be aircraft that had been switched off or had flown out of
the box and back.
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
    RfPayload,
    SourceType,
    TrackPayload,
    ValidationStatus,
)
from app.detection.track_gap import (
    FINDING_TYPE,
    RULE_ID,
    BoundingBox,
    GapPolicy,
    GapShape,
    RuleError,
    TrackGapFinding,
    detect_track_gaps,
)

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
TICK = timedelta(seconds=10)

#: The corpus bounding box, from `data/opensky/manifest.json`, and a point
#: comfortably inside it. The margin is `adp-008`'s, so the two agree about
#: what "interior" means.
BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
INSIDE = Location(lat=52.0, lon=5.0)
ALSO_INSIDE = Location(lat=51.5, lon=6.0)
#: Inside the box but within the 0.25 degree margin of its southern edge --
#: an aircraft here is about to leave, and an interval after it means
#: nothing went wrong.
NEAR_EDGE = Location(lat=49.1, lon=5.0)

POLICY = GapPolicy(
    threshold=timedelta(seconds=100),
    contact_fresh_within=timedelta(seconds=30),
    box=BOX,
)

AIRCRAFT = "AC-000000000001"
OTHER = "AC-000000000002"


def track(
    *,
    aircraft_id: str = AIRCRAFT,
    timestamp: datetime = START,
    position_staleness_s: float = 1.0,
    contact_staleness_s: float = 0.0,
    on_ground: bool = False,
    location: Location = INSIDE,
) -> CanonicalObservation:
    return CanonicalObservation(
        source_id="opensky-replay",
        source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK,
        timestamp=timestamp,
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
            aircraft_id=aircraft_id,
            flight_id="FL-000000000001",
            altitude_m=10000.0,
            velocity_ms=200.0,
            heading_deg=90.0,
            vertical_rate_ms=0.0,
            on_ground=on_ground,
            position_staleness_s=position_staleness_s,
            contact_staleness_s=contact_staleness_s,
        ),
    )


def nominal(count: int, *, aircraft_id: str = AIRCRAFT, start: datetime = START) -> list[CanonicalObservation]:
    """A healthy stream: reporting every tick, both clocks fresh."""
    return [
        track(aircraft_id=aircraft_id, timestamp=start + i * TICK)
        for i in range(count)
    ]


# --------------------------------------------- frozen position, mechanism A
#
# The gnss-degradation shape: still transmitting, position stopped advancing.


def test_a_stale_position_with_fresh_contact_is_a_frozen_position_finding() -> None:
    # spec: anom-010, FR-304
    stream = [*nominal(3), track(timestamp=START + 3 * TICK, position_staleness_s=150.0)]

    (finding,) = detect_track_gaps(stream, POLICY)

    assert finding.shape is GapShape.FROZEN_POSITION


def test_a_stale_position_with_equally_stale_contact_is_not_frozen() -> None:
    """The amended failure case, and the reason both clocks are carried.

    Both stale means the aircraft is not being heard from, which is the
    other shape entirely. Requiring fresh contact is also what takes the
    measured quiet-run background from 137.7 aircraft per run to 24.6.
    """
    # spec: anom-010, dal-001
    stream = [
        *nominal(3),
        track(timestamp=START + 3 * TICK, position_staleness_s=150.0, contact_staleness_s=150.0),
    ]

    assert detect_track_gaps(stream, POLICY) == ()


def test_a_position_staleness_below_the_threshold_raises_nothing() -> None:
    # spec: anom-010
    stream = [*nominal(3), track(timestamp=START + 3 * TICK, position_staleness_s=99.0)]

    assert detect_track_gaps(stream, POLICY) == ()


def test_consecutive_frozen_readings_are_one_finding() -> None:
    """A frozen position reports every tick it stays frozen. One event."""
    # spec: anom-010
    stream = [
        *nominal(2),
        *[
            track(timestamp=START + i * TICK, position_staleness_s=100.0 + 10 * i)
            for i in range(2, 8)
        ],
    ]

    assert len(detect_track_gaps(stream, POLICY)) == 1


def test_a_frozen_finding_begins_when_the_position_was_last_fresh() -> None:
    """Not when the rule noticed. The reported staleness says how far back
    the last good fix was, and that is the onset of the event."""
    # spec: anom-010, FR-309
    noticed = START + 20 * TICK
    stream = [*nominal(20), track(timestamp=noticed, position_staleness_s=150.0)]

    (finding,) = detect_track_gaps(stream, POLICY)

    assert finding.started_at == noticed - timedelta(seconds=150)
    assert finding.ended_at == noticed


def test_an_aircraft_on_the_ground_is_never_frozen() -> None:
    """A parked aircraft stops reporting a fresh position because it has
    been switched off, which is the uninteresting reason."""
    # spec: anom-010, adp-008
    stream = [
        *nominal(3),
        track(timestamp=START + 3 * TICK, position_staleness_s=300.0, on_ground=True),
    ]

    assert detect_track_gaps(stream, POLICY) == ()


# ------------------------------------------------- not heard, mechanism B
#
# The aircraft-coverage-gap shape: the rows stop arriving, so there is no
# field left to read and the gap is the absence itself.


def test_an_interval_past_the_threshold_is_a_not_heard_finding() -> None:
    # spec: anom-010, FR-304
    stream = [*nominal(3), track(timestamp=START + 3 * TICK + timedelta(seconds=200))]

    (finding,) = detect_track_gaps(stream, POLICY)

    assert finding.shape is GapShape.NOT_HEARD
    assert finding.started_at == START + 2 * TICK
    assert finding.ended_at == START + 3 * TICK + timedelta(seconds=200)


def test_an_interval_below_the_threshold_raises_nothing() -> None:
    # spec: anom-010
    stream = [*nominal(3), track(timestamp=START + 2 * TICK + timedelta(seconds=99))]

    assert detect_track_gaps(stream, POLICY) == ()


def test_the_last_report_before_the_window_closes_raises_nothing() -> None:
    """The item's first named failure case. Every aircraft still in flight
    is stale when the run ends, so a rule that extrapolated a trailing gap
    would fire on all of them at once."""
    # spec: anom-010
    assert detect_track_gaps(nominal(5), POLICY) == ()


def test_a_gap_bracketed_by_a_grounded_report_raises_nothing() -> None:
    # spec: anom-010, adp-008
    stream = [
        *nominal(3),
        track(timestamp=START + 2 * TICK + timedelta(seconds=5), on_ground=True),
        track(timestamp=START + 2 * TICK + timedelta(seconds=305), on_ground=True),
    ]

    assert detect_track_gaps(stream, POLICY) == ()


def test_a_gap_at_the_edge_of_the_box_raises_nothing() -> None:
    """The item's second named failure case. An aircraft that flies out of
    the box and back leaves an interval with nothing in it, and nothing
    went wrong -- the same correction the bounding-box sweep needed when a
    naive measure reported 3,140 s gaps in a 3,600 s file."""
    # spec: anom-010, adp-008
    stream = [
        track(timestamp=START, location=NEAR_EDGE),
        track(timestamp=START + timedelta(seconds=200), location=NEAR_EDGE),
    ]

    assert detect_track_gaps(stream, POLICY) == ()


def test_a_gap_with_one_end_near_the_edge_raises_nothing() -> None:
    """Both ends must be interior. One is not enough: an aircraft leaving
    the box has one end inside it by definition."""
    # spec: anom-010
    stream = [
        track(timestamp=START, location=INSIDE),
        track(timestamp=START + timedelta(seconds=200), location=NEAR_EDGE),
    ]

    assert detect_track_gaps(stream, POLICY) == ()


def test_without_a_box_the_interior_test_does_not_apply() -> None:
    """Synthetic streams have no corpus box. The filter is a corpus
    correction, so it is configuration rather than an assumption."""
    # spec: anom-010
    boxless = GapPolicy(
        threshold=timedelta(seconds=100), contact_fresh_within=timedelta(seconds=30)
    )
    stream = [
        track(timestamp=START, location=NEAR_EDGE),
        track(timestamp=START + timedelta(seconds=200), location=NEAR_EDGE),
    ]

    assert len(detect_track_gaps(stream, boxless)) == 1


def test_a_not_heard_finding_locates_the_last_known_position() -> None:
    """Where the aircraft was last seen, not where it reappeared. The
    finding is about the interval, and the interval starts there."""
    # spec: anom-010
    stream = [
        track(timestamp=START, location=INSIDE),
        track(timestamp=START + timedelta(seconds=200), location=ALSO_INSIDE),
    ]

    (finding,) = detect_track_gaps(stream, POLICY)

    assert finding.location == INSIDE


# ------------------------------------------------------------------ shared


def test_each_aircraft_is_considered_separately() -> None:
    """Two aircraft reporting alternately must not have one's interval
    measured against the other's report."""
    # spec: anom-010
    stream = [
        track(aircraft_id=AIRCRAFT, timestamp=START),
        track(aircraft_id=OTHER, timestamp=START + timedelta(seconds=100)),
        track(aircraft_id=AIRCRAFT, timestamp=START + timedelta(seconds=200)),
        track(aircraft_id=OTHER, timestamp=START + timedelta(seconds=210)),
    ]

    findings = detect_track_gaps(stream, POLICY)

    assert [f.aircraft_id for f in findings] == [AIRCRAFT]


def test_one_aircraft_with_two_separate_gaps_yields_two_findings() -> None:
    """One finding per discontinuity, not one per stale aircraft, because
    anom-004 clusters by location and two gaps in two places are two
    pieces of spatial evidence."""
    # spec: anom-010, anom-004
    stream = [
        track(timestamp=START),
        track(timestamp=START + timedelta(seconds=200)),
        track(timestamp=START + timedelta(seconds=210)),
        track(timestamp=START + timedelta(seconds=500)),
    ]

    assert len(detect_track_gaps(stream, POLICY)) == 2


def test_a_finding_carries_its_duration() -> None:
    # spec: anom-010
    stream = [track(timestamp=START), track(timestamp=START + timedelta(seconds=240))]

    (finding,) = detect_track_gaps(stream, POLICY)

    assert finding.duration == timedelta(seconds=240)


def test_a_finding_carries_the_type_and_rule_the_spec_names() -> None:
    # spec: anom-010, FR-402
    stream = [track(timestamp=START), track(timestamp=START + timedelta(seconds=200))]

    (finding,) = detect_track_gaps(stream, POLICY)

    assert (finding.finding_type, finding.rule_id) == (FINDING_TYPE, RULE_ID)
    assert (FINDING_TYPE, RULE_ID) == ("track_continuity_gap", "TRACK-GAP")


def test_a_finding_carries_no_severity() -> None:
    """It is intermediate, not reportable. Severity is what an analyst is
    shown, and nothing here is shown to one -- a quiet run produces around
    138 of these by the measurement recorded on anom-008.
    """
    # spec: anom-010, anom-008, ui-001
    stream = [track(timestamp=START), track(timestamp=START + timedelta(seconds=200))]

    (finding,) = detect_track_gaps(stream, POLICY)

    assert not hasattr(finding, "severity")


def test_the_order_reports_arrive_in_is_not_an_input() -> None:
    """Two aircraft, because with one there is no ordering between
    aircraft to get wrong -- the mistake anom-001's single-cell version of
    this test could not catch."""
    # spec: anom-010, FR-301, NFR-601
    stream = [
        track(aircraft_id=AIRCRAFT, timestamp=START),
        track(aircraft_id=AIRCRAFT, timestamp=START + timedelta(seconds=200)),
        track(aircraft_id=OTHER, timestamp=START),
        track(aircraft_id=OTHER, timestamp=START + timedelta(seconds=300)),
    ]

    forward = detect_track_gaps(stream, POLICY)
    backward = detect_track_gaps(list(reversed(stream)), POLICY)

    assert forward == backward
    assert [f.aircraft_id for f in forward] == [AIRCRAFT, OTHER]


def test_an_rf_observation_is_refused() -> None:
    """The same argument the other two detectors make: a radio reading
    belongs to no aircraft, so skipping it would judge less than the
    caller supplied without saying so."""
    # spec: anom-010
    rf = CanonicalObservation(
        source_id="synthetic-rf",
        source_type=SourceType.SYNTHETIC_RF,
        observation_type=ObservationType.RF,
        timestamp=START,
        location=INSIDE,
        data_mode=DataMode.SYNTHETIC,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="synthetic-rf",
            source_type=SourceType.SYNTHETIC_RF,
            data_mode=DataMode.SYNTHETIC,
            scenario_run_id=1,
        ),
        payload=RfPayload(
            sensor_id="RF-01",
            channel_index=0,
            centre_frequency_mhz=1567.42,
            band="GNSS-L1",
            power_dbm=-95.0,
            snr_db=20.0,
            bandwidth_mhz=2.0,
            signal_type="noise",
            baseline_delta_db=0.0,
        ),
    )

    with pytest.raises(RuleError):
        detect_track_gaps([*nominal(2), rf], POLICY)


def test_a_non_positive_threshold_is_refused() -> None:
    """A zero threshold makes every interval a gap."""
    # spec: anom-010
    for bad in (timedelta(0), timedelta(seconds=-10)):
        with pytest.raises(RuleError):
            GapPolicy(threshold=bad, contact_fresh_within=timedelta(seconds=30))


def test_a_contact_window_at_or_above_the_threshold_is_refused() -> None:
    """If contact may be as stale as the threshold, the two shapes stop
    being exclusive and one event is reported as both."""
    # spec: anom-010
    with pytest.raises(RuleError):
        GapPolicy(
            threshold=timedelta(seconds=100), contact_fresh_within=timedelta(seconds=100)
        )


def test_a_finding_is_immutable() -> None:
    # spec: anom-010
    stream = [track(timestamp=START), track(timestamp=START + timedelta(seconds=200))]

    (finding,) = detect_track_gaps(stream, POLICY)

    assert isinstance(finding, TrackGapFinding)
    with pytest.raises(Exception):
        finding.aircraft_id = "AC-tampered"  # type: ignore[misc]


def test_the_two_shapes_are_exclusive_for_one_event() -> None:
    """An aircraft that stops being heard from has both clocks running on,
    so the absence is reported once as not_heard and never additionally as
    a frozen position when it returns."""
    # spec: anom-010, anom-005, anom-006
    stream = [
        track(timestamp=START),
        track(
            timestamp=START + timedelta(seconds=200),
            position_staleness_s=200.0,
            contact_staleness_s=200.0,
        ),
    ]

    findings = detect_track_gaps(stream, POLICY)

    assert [f.shape for f in findings] == [GapShape.NOT_HEARD]
