"""The sensor-fault rule, `SENSOR-FAULT`. Spec: anom-007.

The rule that separates a broken receiver from a cause out in the world,
and the first rule in the project that judges the *shape* of an
abnormality rather than its size. `anom-001` decides whether a reading is
abnormal; this decides what the pattern of abnormality implicates.

Two pieces of evidence, kept apart deliberately. **Geography**: a receiver
loud while its close neighbours read nominal is describing itself, not the
air, and three adjacent receivers loud together is the environment and
must raise nothing. **Frequency**: a real emission spills into the
channels either side of it, so a lone loud channel between two clean ones
is a pattern the physics does not easily produce -- while the whole plan
rising together is the weaker claim, because a wideband emitter parked
beside the receiver looks the same from here.

Most of the tests below are about what the rule refuses to conclude. The
one that matters most is `test_an_unjudged_neighbour_is_not_a_clean_one`:
`anom-001` reports the cells it could not judge precisely so that silence
is never read as cleanliness, and this is the first consumer with the
opportunity to make that mistake.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.dal.models import Location
from app.detection.baseline import RfCell, RfMetric
from app.detection.rf_noise import (
    ReadingRef,
    RfNoiseAnomaly,
    RfNoiseFindings,
    Severity,
    UnjudgedCell,
)
from app.detection.sensor_fault import (
    ANOMALY_TYPE,
    RULE_ID,
    Confidence,
    Dismissal,
    FaultError,
    FaultPolicy,
    SensorFault,
    Verdict,
    detect_sensor_faults,
)
from app.scenario.layout import load_layout

LAYOUT = load_layout()

#: The GNSS L1 channel, which is what `scn-002` stages a narrowband
#: incident on. Its neighbours in the plan are 3 and 5.
L1 = 4

START = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
#: The staged window: 120 s into the run, 300 s long (`scn-002` defaults).
WINDOW_START = START + timedelta(seconds=120)
WINDOW_END = START + timedelta(seconds=420)

#: Measured from the shipped layout, not assumed. At 70 km -- the layout's
#: own discrimination radius -- RF-01 has RF-02 (45.3 km) and RF-03
#: (54.1 km); RF-04 has only RF-05 (55.7 km); RF-01 and RF-04 are 104.3 km
#: apart and are not neighbours of each other.
NEAR = 70.0
#: Wide enough to make RF-01 and RF-04 neighbours.
WIDE = 110.0
#: Narrower than the closest pair in the layout, so nothing has a
#: neighbour and the rule has nothing to compare against.
BLIND = 40.0


def loud(
    *,
    sensor: str,
    channel: int = L1,
    started_at: datetime = WINDOW_START,
    ended_at: datetime = WINDOW_END,
    deviation: float = 8.0,
) -> RfNoiseAnomaly:
    """One `anom-001` episode, as that rule would emit it."""
    site = LAYOUT.site(sensor)
    cell = RfCell(sensor, channel)
    return RfNoiseAnomaly(
        cell=cell,
        metric=RfMetric.POWER_DBM,
        severity=Severity.HIGH,
        started_at=started_at,
        ended_at=ended_at,
        location=Location(lat=site.lat, lon=site.lon),
        peak_deviation=deviation,
        triggering=(
            ReadingRef(sensor_id=sensor, channel_index=channel, timestamp=started_at),
        ),
    )


def blind_cell(sensor: str, channel: int = L1) -> UnjudgedCell:
    """A cell `anom-001` could not assess. Not the same as a quiet one."""
    return UnjudgedCell(
        cell=RfCell(sensor, channel),
        reason="baseline had 4 of 30 samples required",
    )


def findings(
    anomalies: tuple[RfNoiseAnomaly, ...] = (),
    unjudged: tuple[UnjudgedCell, ...] = (),
) -> RfNoiseFindings:
    return RfNoiseFindings(anomalies=anomalies, unjudged=unjudged)


def policy(radius: float | None = NEAR) -> FaultPolicy:
    return FaultPolicy(neighbour_radius_km=radius)


# --- the spatial test ---------------------------------------------------


def test_a_lone_loud_receiver_with_clean_neighbours_is_a_fault() -> None:
    # spec: anom-007 -- the rule's whole purpose, in one case.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)), LAYOUT, policy()
    )

    assert len(result.faults) == 1
    fault = result.faults[0]
    assert fault.sensor_id == "RF-01"
    assert fault.rule_id == RULE_ID
    assert fault.anomaly_type == ANOMALY_TYPE
    assert result.dismissed == ()


def test_an_abnormal_neighbour_makes_it_environmental_not_a_fault() -> None:
    # spec: anom-007 -- the item's first failure case, minimal form.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"), loud(sensor="RF-02"))), LAYOUT, policy()
    )

    assert result.faults == ()
    assert {d.sensor_id for d in result.dismissed} == {"RF-01", "RF-02"}
    assert {d.verdict for d in result.dismissed} == {Verdict.ENVIRONMENTAL}


def test_several_adjacent_sensors_abnormal_raise_no_fault_at_all() -> None:
    # spec: anom-007 -- the failure case as the item words it. RF-04, RF-05
    # and RF-06 form a chain in which each is a neighbour of the next.
    result = detect_sensor_faults(
        findings(
            (loud(sensor="RF-04"), loud(sensor="RF-05"), loud(sensor="RF-06"))
        ),
        LAYOUT,
        policy(),
    )

    assert result.faults == ()
    assert len(result.dismissed) == 3
    assert all(d.verdict is Verdict.ENVIRONMENTAL for d in result.dismissed)


def test_a_neighbour_loud_in_a_different_window_does_not_excuse_the_fault() -> None:
    # spec: anom-007 -- the neighbour test is per window, not per run. A
    # receiver that was loud an hour earlier says nothing about now.
    later = WINDOW_END + timedelta(seconds=600)
    result = detect_sensor_faults(
        findings(
            (
                loud(sensor="RF-01"),
                loud(
                    sensor="RF-02",
                    started_at=later,
                    ended_at=later + timedelta(seconds=300),
                ),
            )
        ),
        LAYOUT,
        policy(),
    )

    assert {f.sensor_id for f in result.faults} == {"RF-01", "RF-02"}


def test_overlap_is_inclusive_at_the_endpoint() -> None:
    # spec: anom-007 -- an episode's end is its last *exceeding* reading,
    # not the first quiet one, so a neighbour ending on the tick this one
    # starts genuinely overlapped it by a reading. Strict comparison here
    # would call that neighbour clean and raise a fault.
    result = detect_sensor_faults(
        findings(
            (
                loud(sensor="RF-01"),
                loud(
                    sensor="RF-02",
                    started_at=WINDOW_START - timedelta(seconds=300),
                    ended_at=WINDOW_START,
                ),
            )
        ),
        LAYOUT,
        policy(),
    )

    assert result.faults == ()


def test_a_sensor_beyond_the_radius_is_not_a_neighbour() -> None:
    # spec: anom-007 -- RF-01 and RF-04 are 104.3 km apart, so at 70 km
    # neither is evidence about the other and both stand alone.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"), loud(sensor="RF-04"))), LAYOUT, policy()
    )

    assert {f.sensor_id for f in result.faults} == {"RF-01", "RF-04"}


def test_a_wider_radius_brings_that_sensor_into_the_test() -> None:
    # spec: anom-007 -- the radius is configuration and it changes the
    # answer, which is what makes it configuration rather than a constant.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"), loud(sensor="RF-04"))), LAYOUT, policy(WIDE)
    )

    assert result.faults == ()


def test_the_radius_defaults_to_the_layout_discrimination_radius() -> None:
    # spec: anom-007 -- `scn-005` already validates that value as leaving
    # every sensor a neighbour inside it and a non-neighbour beyond, so the
    # default defers to validated configuration rather than inventing one.
    left = detect_sensor_faults(findings((loud(sensor="RF-01"),)), LAYOUT, policy(None))
    right = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)),
        LAYOUT,
        policy(LAYOUT.discrimination_radius_km),
    )

    assert left.faults[0].spatial.radius_km == LAYOUT.discrimination_radius_km
    assert left == right


def test_no_neighbour_inside_the_radius_is_undecided_not_a_fault() -> None:
    # spec: anom-007 -- the vacuous case. No neighbours means no abnormal
    # neighbours, which read as a pass would make every RF anomaly in the
    # layout a sensor fault.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)), LAYOUT, policy(BLIND)
    )

    assert result.faults == ()
    assert len(result.dismissed) == 1
    assert result.dismissed[0].verdict is Verdict.UNDECIDED
    assert "40" in result.dismissed[0].reason


# --- what silence is not ------------------------------------------------


def test_an_unjudged_neighbour_is_not_a_clean_one() -> None:
    # spec: anom-007 -- `anom-001` reports what it could not judge so that
    # nothing downstream mistakes silence for cleanliness. This is the
    # first consumer able to make that mistake.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),), (blind_cell("RF-02"),)), LAYOUT, policy()
    )

    assert result.faults == ()
    assert len(result.dismissed) == 1
    assert result.dismissed[0].verdict is Verdict.UNDECIDED
    assert "RF-02" in result.dismissed[0].reason


def test_an_abnormal_neighbour_outranks_an_unjudged_one() -> None:
    # spec: anom-007 -- positive evidence of an environmental cause settles
    # it; missing data elsewhere does not turn that into a maybe.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"), loud(sensor="RF-03")), (blind_cell("RF-02"),)),
        LAYOUT,
        policy(),
    )

    assert result.faults == ()
    assert [d.verdict for d in result.dismissed if d.sensor_id == "RF-01"] == [
        Verdict.ENVIRONMENTAL
    ]


def test_an_unjudged_cell_beyond_the_radius_is_irrelevant() -> None:
    # spec: anom-007 -- only the neighbours are the neighbour test. RF-07
    # is 229.6 km from RF-01.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),), (blind_cell("RF-07"),)), LAYOUT, policy()
    )

    assert [f.sensor_id for f in result.faults] == ["RF-01"]


def test_the_unjudged_neighbours_are_named_in_the_evidence() -> None:
    # spec: anom-007 -- a dismissal a reader cannot check is an assertion.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),), (blind_cell("RF-02"),)), LAYOUT, policy()
    )

    assert result.dismissed[0].spatial.unjudged == ("RF-02",)
    assert result.dismissed[0].spatial.neighbours == ("RF-02", "RF-03")


# --- the frequency test -------------------------------------------------


def test_a_lone_channel_between_clean_ones_is_high_confidence() -> None:
    # spec: anom-007 -- the pattern a real emission does not easily make.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)), LAYOUT, policy()
    )

    fault = result.faults[0]
    assert fault.confidence is Confidence.HIGH
    assert fault.spectral.channels == (L1,)
    assert fault.spectral.adjacent_checked == (3, 5)
    assert fault.spectral.adjacent_abnormal == ()


def test_the_whole_plan_rising_together_is_low_confidence() -> None:
    # spec: anom-007 -- the item's second failure case. A wideband emitter
    # beside the receiver produces this too, so it is the weaker claim.
    result = detect_sensor_faults(
        findings(tuple(loud(sensor="RF-01", channel=c) for c in range(8))),
        LAYOUT,
        policy(),
    )

    assert len(result.faults) == 1
    assert result.faults[0].confidence is Confidence.LOW
    assert result.faults[0].spectral.channels == tuple(range(8))


def test_a_partial_spread_is_medium_confidence() -> None:
    # spec: anom-007 -- between the two: the deviation reached an adjacent
    # channel but not the plan.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01", channel=3), loud(sensor="RF-01", channel=4))),
        LAYOUT,
        policy(),
    )

    fault = result.faults[0]
    assert fault.confidence is Confidence.MEDIUM
    assert fault.spectral.adjacent_abnormal == (3, 4)


def test_broadband_and_single_channel_do_not_share_a_confidence() -> None:
    # spec: anom-007 -- the failure case stated as the item states it,
    # rather than only through the two bands separately.
    single = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)), LAYOUT, policy()
    )
    whole = detect_sensor_faults(
        findings(tuple(loud(sensor="RF-01", channel=c) for c in range(8))),
        LAYOUT,
        policy(),
    )

    assert single.faults[0].confidence is not whole.faults[0].confidence


def test_an_unjudged_adjacent_channel_prevents_the_high_claim() -> None:
    # spec: anom-007 -- isolation cannot be claimed over a channel nobody
    # assessed: the unjudged neighbour might have been loud.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),), (blind_cell("RF-01", 5),)),
        LAYOUT,
        policy(),
    )

    fault = result.faults[0]
    assert fault.confidence is Confidence.MEDIUM
    assert fault.spectral.adjacent_unjudged == (5,)


def test_an_end_of_plan_channel_has_one_adjacent_channel() -> None:
    # spec: anom-007 -- channel 0 has only channel 1 beside it, and a
    # missing neighbour at the edge of the plan is not a missing reading.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01", channel=0),)), LAYOUT, policy()
    )

    fault = result.faults[0]
    assert fault.spectral.adjacent_checked == (1,)
    assert fault.confidence is Confidence.HIGH


def test_the_two_tests_are_two_records() -> None:
    # spec: anom-007 -- the frequency test is recorded distinctly rather
    # than folded into the spatial one, because they are evidence of
    # different kinds and the bundle must show which carries the argument.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)), LAYOUT, policy()
    )

    fault = result.faults[0]
    assert fault.spatial.neighbours == ("RF-02", "RF-03")
    assert fault.spatial.abnormal == ()
    assert fault.spectral.channels == (L1,)
    assert type(fault.spatial) is not type(fault.spectral)


def test_confidence_is_never_a_number() -> None:
    # spec: anom-007, ui-001 -- three words, and nothing else representable.
    assert {c.value for c in Confidence} == {"low", "medium", "high"}


# --- the unit of judgement ----------------------------------------------


def test_one_receiver_loud_on_eight_channels_is_one_fault() -> None:
    # spec: anom-007 -- a fault is a property of a box. Per-episode output
    # would make one broken receiver read as eight sensor faults.
    result = detect_sensor_faults(
        findings(tuple(loud(sensor="RF-01", channel=c) for c in range(8))),
        LAYOUT,
        policy(),
    )

    assert len(result.faults) == 1


def test_two_episodes_with_quiet_between_them_are_two_faults() -> None:
    # spec: anom-007 -- the same argument `anom-001` makes at reading
    # level: one window must not span the quiet hour in the middle of it.
    second = WINDOW_END + timedelta(seconds=600)
    result = detect_sensor_faults(
        findings(
            (
                loud(sensor="RF-01"),
                loud(
                    sensor="RF-01",
                    started_at=second,
                    ended_at=second + timedelta(seconds=300),
                ),
            )
        ),
        LAYOUT,
        policy(),
    )

    assert len(result.faults) == 2
    assert result.faults[0].ended_at < result.faults[1].started_at


def test_the_window_spans_the_episodes_that_made_it() -> None:
    # spec: anom-007 -- the merged window is the union of its parts, so a
    # reader can find every contributing reading from the fault alone.
    early = loud(
        sensor="RF-01",
        channel=3,
        started_at=WINDOW_START,
        ended_at=WINDOW_START + timedelta(seconds=100),
    )
    late = loud(
        sensor="RF-01",
        channel=4,
        started_at=WINDOW_START + timedelta(seconds=50),
        ended_at=WINDOW_END,
    )
    result = detect_sensor_faults(findings((early, late)), LAYOUT, policy())

    assert len(result.faults) == 1
    assert result.faults[0].started_at == WINDOW_START
    assert result.faults[0].ended_at == WINDOW_END


def test_the_fault_is_located_at_the_receiver() -> None:
    # spec: anom-007 -- one sensor's fault is at that sensor and nowhere
    # else; an area would claim ground nothing was observed across.
    site = LAYOUT.site("RF-01")
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)), LAYOUT, policy()
    )

    assert result.faults[0].location == Location(lat=site.lat, lon=site.lon)


# --- refusals and structure ---------------------------------------------


def test_a_quiet_run_produces_nothing_and_says_so() -> None:
    # spec: anom-007, anom-008 -- no anomalies is not the same as not
    # having looked, and this rule has nothing to look at without them.
    result = detect_sensor_faults(findings(), LAYOUT, policy())

    assert result.faults == ()
    assert result.dismissed == ()


def test_an_anomaly_from_outside_the_layout_is_refused() -> None:
    # spec: anom-007 -- findings and layout that disagree are a caller bug.
    # Skipping the sensor would judge fewer receivers than were reported,
    # without saying so.
    stray = dataclasses.replace(loud(sensor="RF-01"), cell=RfCell("RF-99", L1))

    with pytest.raises(FaultError, match="RF-99"):
        detect_sensor_faults(findings((stray,)), LAYOUT, policy())


def test_a_non_positive_radius_is_refused() -> None:
    # spec: anom-007 -- a zero radius has no neighbours by construction and
    # would make every anomaly undecided rather than failing loudly.
    with pytest.raises(FaultError):
        FaultPolicy(neighbour_radius_km=0.0)


def test_the_rule_cannot_see_track_evidence() -> None:
    # spec: anom-007, anom-013 -- the ordering puts this rule first because
    # it decides on the RF pattern alone. Enforced by what it can be handed
    # rather than by remembering not to look.
    parameters = set(inspect.signature(detect_sensor_faults).parameters)
    fields = {f.name for f in dataclasses.fields(SensorFault)}
    fields |= {f.name for f in dataclasses.fields(FaultPolicy)}

    assert parameters == {"findings", "layout", "policy"}
    assert not any(
        word in name
        for name in fields
        for word in ("track", "aircraft", "cluster", "gap", "excess")
    )


def test_the_output_does_not_depend_on_the_order_of_the_input() -> None:
    # spec: anom-007, NFR-601 -- determinism. The same findings in a
    # different order are the same findings.
    anomalies = (
        loud(sensor="RF-04"),
        loud(sensor="RF-01", channel=3),
        loud(sensor="RF-01", channel=4),
        loud(sensor="RF-07"),
    )
    forwards = detect_sensor_faults(findings(anomalies), LAYOUT, policy())
    backwards = detect_sensor_faults(findings(tuple(reversed(anomalies))), LAYOUT, policy())

    assert forwards == backwards
    assert [f.sensor_id for f in forwards.faults] == ["RF-01", "RF-04", "RF-07"]


def test_a_fault_is_frozen() -> None:
    # spec: anom-007 -- a detection value object is evidence, and evidence
    # that can be edited after the fact is not evidence.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)), LAYOUT, policy()
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.faults[0].sensor_id = "RF-02"  # type: ignore[misc]


def test_a_dismissal_always_carries_its_reason() -> None:
    # spec: anom-007 -- the dismissals are this rule's half of the audit
    # trail for `anom-013`: the ladder must be able to say why a zone was
    # not claimed here before offering it to the next rule.
    result = detect_sensor_faults(
        findings((loud(sensor="RF-01"), loud(sensor="RF-02"))), LAYOUT, policy()
    )

    assert all(isinstance(d, Dismissal) and d.reason for d in result.dismissed)
    assert any("RF-02" in d.reason for d in result.dismissed if d.sensor_id == "RF-01")
