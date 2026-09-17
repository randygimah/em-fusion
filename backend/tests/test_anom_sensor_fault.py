"""The sensor-fault rule, `SENSOR-FAULT`. Spec: anom-007.

The rule that separates a broken receiver from a cause out in the world,
and the first rule in the project that judges the *shape* of an
abnormality rather than its size. `anom-001` decides whether a reading is
abnormal; this decides what the pattern of abnormality implicates.

Two pieces of evidence, kept apart deliberately. **Geography**: a receiver
away from its normal while its close neighbours sit at theirs is
describing itself, not the air, and receivers going together is the
environment and must raise nothing. **Frequency**: a real emission spills
into the channels either side of it, so a lone raised channel between two
normal ones is a pattern the physics does not easily produce -- while the
whole plan rising together is the weaker claim, because a wideband emitter
parked beside the receiver looks the same from here.

**Nominality is measured from readings, not from another rule's episodes,
and that is a correction rather than a preference.** Built the other way,
the rule claimed 21 of 60 interference runs as broken receivers: the
injected elevation varies per tick, roughly one tick in six falls short of
`anom-001`'s threshold, and a receiver loud for a whole incident therefore
emits a string of short episodes rather than one. Two receivers loud
through the same window can then have fragments that never overlap, and
each reads as isolated. The neighbours in those windows were sitting 2.5
to 6 dB above their own baselines and not one of them exceeded the anomaly
threshold there. Asking "was this receiver anomalous" in place of "was
this receiver nominal" is the whole of the defect.

Most of the tests below are about what the rule refuses to conclude.
"""

from __future__ import annotations

import dataclasses
import inspect
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
from app.detection.baseline import Baseline, BaselineTable, RfCell, RfMetric
from app.detection.rf_noise import (
    ReadingRef,
    RfNoiseAnomaly,
    RfNoiseFindings,
    Severity,
    UnjudgedCell,
)
from app.detection.sensor_fault import (
    ANOMALY_TYPE,
    DEFAULT_NOMINAL_WITHIN_DB,
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
SENSORS = tuple(site.sensor_id for site in LAYOUT.sensors)
CHANNELS = tuple(channel.index for channel in LAYOUT.channels)

#: The GNSS L1 channel, which is what `scn-002` stages a narrowband
#: incident on. Its neighbours in the plan are 3 and 5.
L1 = 4

#: The quiet nominal `scn-001`'s emitter produces, and the spread measured
#: over the twenty quiet runs.
QUIET_DBM = -95.0
QUIET_SNR = 12.0
QUIET_SPREAD = 1.5

START = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
TICK = timedelta(seconds=10)
RUN_END = START + timedelta(seconds=900)
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

#: The staged elevation. Well past the 2 dB nominality bar and past
#: `anom-001`'s 6 dB threshold.
STAGED_DB = 8.0
#: Past the nominality bar and short of the anomaly threshold: the case
#: the corpus produced and the episode-based test could not see.
SUB_THRESHOLD_DB = 5.0


def baselines(
    metric: RfMetric = RfMetric.POWER_DBM,
    without: tuple[RfCell, ...] = (),
) -> BaselineTable:
    """A baseline for every cell in the layout, as `anom-002` builds one."""
    mean = QUIET_DBM if metric is RfMetric.POWER_DBM else QUIET_SNR
    table = {
        RfCell(sensor, channel): Baseline(
            cell=RfCell(sensor, channel),
            metric=metric,
            mean=mean,
            stdev=QUIET_SPREAD,
            samples=1800,
        )
        for sensor in SENSORS
        for channel in CHANNELS
        if RfCell(sensor, channel) not in without
    }
    return BaselineTable(
        metric=metric, window=timedelta(hours=1), ending_at=RUN_END, baselines=table
    )


def grid(
    elevate: dict[tuple[str, int], float] | None = None,
    window: tuple[datetime, datetime] = (WINDOW_START, WINDOW_END),
    omit: tuple[str, ...] = (),
) -> tuple[CanonicalObservation, ...]:
    """The dense sensor x channel x time grid `scn-005` specifies.

    Every cell reads its quiet nominal, except those named in `elevate`,
    which are raised by that many dB inside the window -- and whose SNR
    falls by the same amount, because noise rising is what drives it down.
    """
    raised = elevate or {}
    observations: list[CanonicalObservation] = []
    for sensor in SENSORS:
        if sensor in omit:
            continue
        site = LAYOUT.site(sensor)
        for channel in CHANNELS:
            at = START
            while at <= RUN_END:
                lift = (
                    raised.get((sensor, channel), 0.0)
                    if window[0] <= at <= window[1]
                    else 0.0
                )
                observations.append(
                    CanonicalObservation(
                        source_id="rf",
                        source_type=SourceType.SYNTHETIC_RF,
                        observation_type=ObservationType.RF,
                        timestamp=at,
                        location=Location(lat=site.lat, lon=site.lon),
                        data_mode=DataMode.SYNTHETIC,
                        validation_status=ValidationStatus.VALID,
                        provenance=Provenance(
                            source_id="rf",
                            source_type=SourceType.SYNTHETIC_RF,
                            data_mode=DataMode.SYNTHETIC,
                            scenario_run_id=1,
                        ),
                        payload=RfPayload(
                            sensor_id=sensor,
                            channel_index=channel,
                            centre_frequency_mhz=1575.42,
                            band="GNSS-L1",
                            power_dbm=QUIET_DBM + lift,
                            snr_db=QUIET_SNR - lift,
                            bandwidth_mhz=2.0,
                            signal_type="noise",
                            baseline_delta_db=lift,
                        ),
                    )
                )
                at += TICK
    return tuple(observations)


def swap(
    base: tuple[CanonicalObservation, ...],
    other: tuple[CanonicalObservation, ...],
    cells: tuple[tuple[str, int], ...],
) -> tuple[CanonicalObservation, ...]:
    """`base`, with the named cells' readings taken from `other`.

    Two grids differ only in when a cell is raised, so this composes runs
    where one receiver's event sits in a different window from another's.
    """
    named = set(cells)

    def cell(o: CanonicalObservation) -> tuple[str, int]:
        return (o.payload.sensor_id, o.payload.channel_index)

    return tuple(o for o in base if cell(o) not in named) + tuple(
        o for o in other if cell(o) in named
    )


def loud(
    *,
    sensor: str,
    channel: int = L1,
    started_at: datetime = WINDOW_START,
    ended_at: datetime = WINDOW_END,
) -> RfNoiseAnomaly:
    """One `anom-001` episode, as that rule would emit it."""
    site = LAYOUT.site(sensor)
    return RfNoiseAnomaly(
        cell=RfCell(sensor, channel),
        metric=RfMetric.POWER_DBM,
        severity=Severity.HIGH,
        started_at=started_at,
        ended_at=ended_at,
        location=Location(lat=site.lat, lon=site.lon),
        peak_deviation=STAGED_DB,
        triggering=(
            ReadingRef(sensor_id=sensor, channel_index=channel, timestamp=started_at),
        ),
    )


def blind_cell(sensor: str, channel: int = L1) -> UnjudgedCell:
    """A cell `anom-001` could not assess."""
    return UnjudgedCell(
        cell=RfCell(sensor, channel),
        reason="baseline had 4 of 30 samples required",
    )


def findings(
    anomalies: tuple[RfNoiseAnomaly, ...] = (),
    unjudged: tuple[UnjudgedCell, ...] = (),
) -> RfNoiseFindings:
    return RfNoiseFindings(anomalies=anomalies, unjudged=unjudged)


def policy(
    radius: float | None = NEAR, bar: float = DEFAULT_NOMINAL_WITHIN_DB
) -> FaultPolicy:
    return FaultPolicy(neighbour_radius_km=radius, nominal_within_db=bar)


def run(
    anomalies: tuple[RfNoiseAnomaly, ...],
    elevate: dict[tuple[str, int], float] | None = None,
    *,
    unjudged: tuple[UnjudgedCell, ...] = (),
    table: BaselineTable | None = None,
    observations: tuple[CanonicalObservation, ...] | None = None,
    radius: float | None = NEAR,
    bar: float = DEFAULT_NOMINAL_WITHIN_DB,
):
    return detect_sensor_faults(
        findings(anomalies, unjudged),
        grid(elevate) if observations is None else observations,
        baselines() if table is None else table,
        LAYOUT,
        policy(radius, bar),
    )


#: The ordinary case: RF-01 raised on L1 alone, everything else nominal.
ONE_LOUD = {("RF-01", L1): STAGED_DB}


# --- the spatial test ---------------------------------------------------


def test_a_lone_raised_receiver_with_nominal_neighbours_is_a_fault() -> None:
    # spec: anom-007 -- the rule's whole purpose, in one case.
    result = run((loud(sensor="RF-01"),), ONE_LOUD)

    assert len(result.faults) == 1
    fault = result.faults[0]
    assert fault.sensor_id == "RF-01"
    assert fault.rule_id == RULE_ID
    assert fault.anomaly_type == ANOMALY_TYPE
    assert result.dismissed == ()


def test_a_raised_neighbour_makes_it_environmental_not_a_fault() -> None:
    # spec: anom-007 -- the item's first failure case, minimal form.
    result = run(
        (loud(sensor="RF-01"), loud(sensor="RF-02")),
        {("RF-01", L1): STAGED_DB, ("RF-02", L1): STAGED_DB},
    )

    assert result.faults == ()
    assert {d.sensor_id for d in result.dismissed} == {"RF-01", "RF-02"}
    assert {d.verdict for d in result.dismissed} == {Verdict.ENVIRONMENTAL}


def test_a_neighbour_raised_below_the_anomaly_threshold_is_not_nominal() -> None:
    # spec: anom-007 -- the corpus case, and the reason this rule reads
    # readings rather than episodes. RF-02 is 5 dB above its own baseline
    # and `anom-001` said nothing about it, because 5 dB is short of the
    # 6 dB threshold. It is still plainly not nominal, and a cause that
    # reached two receivers is not a broken one.
    result = run(
        (loud(sensor="RF-01"),),
        {("RF-01", L1): STAGED_DB, ("RF-02", L1): SUB_THRESHOLD_DB},
    )

    assert result.faults == ()
    assert result.dismissed[0].verdict is Verdict.ENVIRONMENTAL
    assert "RF-02" in result.dismissed[0].reason


def test_several_adjacent_receivers_raised_produce_no_fault_at_all() -> None:
    # spec: anom-007 -- the failure case as the item words it. RF-04, RF-05
    # and RF-06 form a chain in which each is a neighbour of the next.
    result = run(
        (loud(sensor="RF-04"), loud(sensor="RF-05"), loud(sensor="RF-06")),
        {(s, L1): STAGED_DB for s in ("RF-04", "RF-05", "RF-06")},
    )

    assert result.faults == ()
    assert len(result.dismissed) == 3
    assert all(d.verdict is Verdict.ENVIRONMENTAL for d in result.dismissed)


def test_a_neighbour_raised_in_a_different_window_does_not_excuse_it() -> None:
    # spec: anom-007 -- nominality is asked about *this* window. A receiver
    # that was raised an hour earlier says nothing about now.
    later = WINDOW_END + timedelta(seconds=120)
    result = run(
        (loud(sensor="RF-01"),),
        observations=swap(
            grid(ONE_LOUD),
            grid({("RF-02", L1): STAGED_DB}, window=(later, RUN_END)),
            (("RF-02", L1),),
        ),
    )

    assert [f.sensor_id for f in result.faults] == ["RF-01"]


def test_a_receiver_beyond_the_radius_is_not_a_neighbour() -> None:
    # spec: anom-007 -- RF-01 and RF-04 are 104.3 km apart, so at 70 km
    # neither is evidence about the other and both stand alone.
    result = run(
        (loud(sensor="RF-01"), loud(sensor="RF-04")),
        {("RF-01", L1): STAGED_DB, ("RF-04", L1): STAGED_DB},
    )

    assert {f.sensor_id for f in result.faults} == {"RF-01", "RF-04"}


def test_a_wider_radius_brings_that_receiver_into_the_test() -> None:
    # spec: anom-007 -- the radius is configuration and it changes the
    # answer, which is what makes it configuration rather than a constant.
    result = run(
        (loud(sensor="RF-01"), loud(sensor="RF-04")),
        {("RF-01", L1): STAGED_DB, ("RF-04", L1): STAGED_DB},
        radius=WIDE,
    )

    assert result.faults == ()


def test_the_radius_defaults_to_the_layout_discrimination_radius() -> None:
    # spec: anom-007 -- `scn-005` already validates that value as leaving
    # every sensor a neighbour inside it and a non-neighbour beyond, so the
    # default defers to validated configuration rather than inventing one.
    left = run((loud(sensor="RF-01"),), ONE_LOUD, radius=None)
    right = run(
        (loud(sensor="RF-01"),), ONE_LOUD, radius=LAYOUT.discrimination_radius_km
    )

    assert left.faults[0].spatial.radius_km == LAYOUT.discrimination_radius_km
    assert left == right


def test_no_neighbour_inside_the_radius_is_undecided_not_a_fault() -> None:
    # spec: anom-007 -- the vacuous case. No neighbours means no raised
    # neighbours, which read as a pass would make every RF anomaly in the
    # layout a broken receiver.
    result = run((loud(sensor="RF-01"),), ONE_LOUD, radius=BLIND)

    assert result.faults == ()
    assert len(result.dismissed) == 1
    assert result.dismissed[0].verdict is Verdict.UNDECIDED
    assert "40" in result.dismissed[0].reason


# --- the bar ------------------------------------------------------------


def test_the_nominality_bar_is_configuration() -> None:
    # spec: anom-007 -- 3 dB of neighbour elevation is above the default
    # bar and below a wider one, and the verdict follows the bar. The
    # default sits in a measured gap: staged neighbours reach 2.51 dB at
    # the 5th percentile, untouched ones 1.58 dB at the 95th.
    staged = {("RF-01", L1): STAGED_DB, ("RF-02", L1): 3.0}
    strict = run((loud(sensor="RF-01"),), staged, bar=2.0)
    lax = run((loud(sensor="RF-01"),), staged, bar=4.0)

    assert strict.faults == ()
    assert len(lax.faults) == 1


def test_the_default_bar_sits_above_the_quiet_spread() -> None:
    # spec: anom-007 -- a bar inside the ordinary wobble of a quiet cell
    # would dismiss every fault as environmental. The measured spread is
    # about 1.5 dB.
    assert DEFAULT_NOMINAL_WITHIN_DB > QUIET_SPREAD


def test_a_neighbour_at_its_baseline_is_nominal() -> None:
    # spec: anom-007 -- the other half of the bar: nothing is inferred
    # from a neighbour reading exactly what it always reads.
    result = run((loud(sensor="RF-01"),), ONE_LOUD)

    assert result.faults[0].spatial.abnormal == ()
    assert dict(result.faults[0].spatial.elevations)["RF-02"] == pytest.approx(0.0)


def test_the_measured_elevation_is_carried_for_every_neighbour() -> None:
    # spec: anom-007 -- "RF-02 sat 5.0 dB above its own normal" is a
    # sentence an analyst can check; "RF-02 was abnormal" is not.
    result = run(
        (loud(sensor="RF-01"),),
        {("RF-01", L1): STAGED_DB, ("RF-02", L1): SUB_THRESHOLD_DB},
    )

    elevations = dict(result.dismissed[0].spatial.elevations)
    assert elevations["RF-02"] == pytest.approx(SUB_THRESHOLD_DB)
    assert elevations["RF-03"] == pytest.approx(0.0)


def test_nominality_is_measured_in_the_direction_the_metric_chooses() -> None:
    # spec: anom-007, anom-001 -- noise rising drives SNR down, so a
    # *fallen* SNR on a neighbour is the same event and a risen one is not.
    # Derived from the baseline table's metric rather than configured: a
    # direction a caller can set wrongly is a silent wrong answer.
    fallen = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)),
        grid({("RF-01", L1): STAGED_DB, ("RF-02", L1): SUB_THRESHOLD_DB}),
        baselines(RfMetric.SNR_DB),
        LAYOUT,
        policy(),
    )
    risen = detect_sensor_faults(
        findings((loud(sensor="RF-01"),)),
        grid({("RF-01", L1): STAGED_DB, ("RF-02", L1): -SUB_THRESHOLD_DB}),
        baselines(RfMetric.SNR_DB),
        LAYOUT,
        policy(),
    )

    assert fallen.faults == ()
    assert len(risen.faults) == 1


# --- what cannot be measured -------------------------------------------


def test_a_neighbour_with_no_baseline_cannot_be_judged_nominal() -> None:
    # spec: anom-007 -- a receiver with nothing to compare against is not
    # a receiver reading normally, and calling it one turns missing data
    # into a fault diagnosis.
    result = run(
        (loud(sensor="RF-01"),),
        ONE_LOUD,
        table=baselines(without=(RfCell("RF-02", L1),)),
    )

    assert result.faults == ()
    assert result.dismissed[0].verdict is Verdict.UNDECIDED
    assert "RF-02" in result.dismissed[0].reason


def test_a_neighbour_with_no_readings_cannot_be_judged_nominal() -> None:
    # spec: anom-007 -- the same argument for a receiver that reported
    # nothing at all in the window.
    result = run((loud(sensor="RF-01"),), observations=grid(ONE_LOUD, omit=("RF-02",)))

    assert result.faults == ()
    assert result.dismissed[0].verdict is Verdict.UNDECIDED
    assert result.dismissed[0].spatial.unjudged == ("RF-02",)


def test_a_raised_neighbour_outranks_one_that_cannot_be_measured() -> None:
    # spec: anom-007 -- positive evidence of an environmental cause settles
    # it; missing data elsewhere does not turn that into a maybe.
    result = run(
        (loud(sensor="RF-01"),),
        {("RF-01", L1): STAGED_DB, ("RF-03", L1): STAGED_DB},
        table=baselines(without=(RfCell("RF-02", L1),)),
    )

    assert result.faults == ()
    assert result.dismissed[0].verdict is Verdict.ENVIRONMENTAL


def test_a_missing_baseline_beyond_the_radius_is_irrelevant() -> None:
    # spec: anom-007 -- only the neighbours are the neighbour test. RF-07
    # is 229.6 km from RF-01.
    result = run(
        (loud(sensor="RF-01"),),
        ONE_LOUD,
        table=baselines(without=(RfCell("RF-07", L1),)),
    )

    assert [f.sensor_id for f in result.faults] == ["RF-01"]


def test_the_neighbours_that_could_not_be_measured_are_named() -> None:
    # spec: anom-007 -- a dismissal a reader cannot check is an assertion.
    result = run(
        (loud(sensor="RF-01"),),
        ONE_LOUD,
        table=baselines(without=(RfCell("RF-02", L1),)),
    )

    assert result.dismissed[0].spatial.unjudged == ("RF-02",)
    assert result.dismissed[0].spatial.neighbours == ("RF-02", "RF-03")


# --- the frequency test -------------------------------------------------


def test_a_lone_channel_between_nominal_ones_is_high_confidence() -> None:
    # spec: anom-007 -- the pattern a real emission does not easily make.
    result = run((loud(sensor="RF-01"),), ONE_LOUD)

    fault = result.faults[0]
    assert fault.confidence is Confidence.HIGH
    assert fault.spectral.channels == (L1,)
    assert fault.spectral.adjacent_checked == (3, 5)
    assert fault.spectral.adjacent_abnormal == ()


def test_the_whole_plan_rising_together_is_low_confidence() -> None:
    # spec: anom-007 -- the item's second failure case. A wideband emitter
    # beside the receiver produces this too, so it is the weaker claim.
    result = run((loud(sensor="RF-01"),), {("RF-01", c): STAGED_DB for c in CHANNELS})

    assert len(result.faults) == 1
    assert result.faults[0].confidence is Confidence.LOW
    assert result.faults[0].spectral.channels == CHANNELS


def test_a_partial_spread_is_medium_confidence() -> None:
    # spec: anom-007 -- between the two: the deviation reached an adjacent
    # channel but not the plan.
    result = run(
        (loud(sensor="RF-01", channel=3), loud(sensor="RF-01")),
        {("RF-01", 3): STAGED_DB, ("RF-01", L1): STAGED_DB},
    )

    fault = result.faults[0]
    assert fault.confidence is Confidence.MEDIUM
    assert fault.spectral.adjacent_abnormal == (3, 4)


def test_broadband_and_single_channel_do_not_share_a_confidence() -> None:
    # spec: anom-007 -- the failure case stated as the item states it,
    # rather than only through the two bands separately.
    single = run((loud(sensor="RF-01"),), ONE_LOUD)
    whole = run((loud(sensor="RF-01"),), {("RF-01", c): STAGED_DB for c in CHANNELS})

    assert single.faults[0].confidence is not whole.faults[0].confidence


def test_the_spread_is_measured_below_the_anomaly_threshold_too() -> None:
    # spec: anom-007 -- the same correction as the neighbour test, one axis
    # over. A 5 dB rise on the adjacent channel is spread the episodes
    # would not show, and spread is what separates an emission from an
    # instrument.
    result = run(
        (loud(sensor="RF-01"),),
        {("RF-01", L1): STAGED_DB, ("RF-01", 5): SUB_THRESHOLD_DB},
    )

    assert result.faults[0].confidence is Confidence.MEDIUM
    assert result.faults[0].spectral.adjacent_abnormal == (L1, 5)


def test_an_adjacent_channel_with_no_baseline_prevents_the_high_claim() -> None:
    # spec: anom-007 -- isolation cannot be claimed over a channel nobody
    # could assess: it might have been raised.
    result = run(
        (loud(sensor="RF-01"),),
        ONE_LOUD,
        table=baselines(without=(RfCell("RF-01", 5),)),
    )

    fault = result.faults[0]
    assert fault.confidence is Confidence.MEDIUM
    assert fault.spectral.adjacent_unjudged == (5,)


def test_an_end_of_plan_channel_has_one_adjacent_channel() -> None:
    # spec: anom-007 -- channel 0 has only channel 1 beside it, and a
    # missing neighbour at the edge of the plan is not a missing reading.
    result = run((loud(sensor="RF-01", channel=0),), {("RF-01", 0): STAGED_DB})

    fault = result.faults[0]
    assert fault.spectral.adjacent_checked == (1,)
    assert fault.confidence is Confidence.HIGH


def test_the_two_tests_are_two_records() -> None:
    # spec: anom-007 -- the frequency test is recorded distinctly rather
    # than folded into the spatial one, because they are evidence of
    # different kinds and the bundle must show which carries the argument.
    result = run((loud(sensor="RF-01"),), ONE_LOUD)

    fault = result.faults[0]
    assert fault.spatial.neighbours == ("RF-02", "RF-03")
    assert fault.spatial.abnormal == ()
    assert fault.spectral.channels == (L1,)
    assert type(fault.spatial) is not type(fault.spectral)


def test_isolation_is_readable_from_the_evidence() -> None:
    # spec: anom-007 -- the bundle (`evb-001`) has to say *why* in words,
    # and "the deviation was isolated to one channel" is the sentence. It
    # is derived from the recorded channels rather than stored beside them,
    # so the summary and the evidence cannot disagree.
    alone = run((loud(sensor="RF-01"),), ONE_LOUD)
    spread = run(
        (loud(sensor="RF-01", channel=3), loud(sensor="RF-01")),
        {("RF-01", 3): STAGED_DB, ("RF-01", L1): STAGED_DB},
    )

    assert alone.faults[0].spectral.isolated is True
    assert alone.faults[0].spectral.broadband is False
    assert spread.faults[0].spectral.isolated is False


def test_confidence_is_never_a_number() -> None:
    # spec: anom-007, ui-001 -- three words, and nothing else representable.
    assert {c.value for c in Confidence} == {"low", "medium", "high"}


# --- the unit of judgement ----------------------------------------------


def test_one_receiver_raised_on_eight_channels_is_one_fault() -> None:
    # spec: anom-007 -- a fault is a property of a box. Per-episode output
    # would make one broken receiver read as eight sensor faults.
    result = run(
        tuple(loud(sensor="RF-01", channel=c) for c in CHANNELS),
        {("RF-01", c): STAGED_DB for c in CHANNELS},
    )

    assert len(result.faults) == 1


def test_a_fragmented_episode_is_one_fault_not_several() -> None:
    # spec: anom-007 -- the corpus defect, at the other end. The injected
    # elevation varies per tick and about one tick in six falls short of
    # `anom-001`'s threshold, so one incident arrives as a string of short
    # episodes. The window is the period the receiver was not nominal,
    # found by the episodes and delimited by the readings.
    fragments = tuple(
        loud(
            sensor="RF-01",
            started_at=WINDOW_START + timedelta(seconds=offset),
            ended_at=WINDOW_START + timedelta(seconds=offset + 20),
        )
        for offset in (0, 60, 120, 240)
    )
    result = run(fragments, ONE_LOUD)

    assert len(result.faults) == 1
    assert result.faults[0].started_at == WINDOW_START
    assert result.faults[0].ended_at == WINDOW_END


def test_two_events_with_a_nominal_period_between_them_are_two_faults() -> None:
    # spec: anom-007 -- the same argument `anom-001` makes at reading
    # level: one window must not span the quiet between two events. The
    # extension stops where the receiver returns to nominal.
    second = WINDOW_END + timedelta(seconds=120)
    early = grid(ONE_LOUD)
    late = grid({("RF-01", L1): STAGED_DB}, window=(second, RUN_END))
    observations = tuple(
        o
        for o in early
        if (o.payload.sensor_id, o.payload.channel_index) != ("RF-01", L1)
        or o.timestamp <= WINDOW_END
    ) + tuple(
        o
        for o in late
        if (o.payload.sensor_id, o.payload.channel_index) == ("RF-01", L1)
        and o.timestamp > WINDOW_END
    )
    result = run(
        (
            loud(sensor="RF-01"),
            loud(sensor="RF-01", started_at=second, ended_at=RUN_END),
        ),
        observations=observations,
    )

    assert len(result.faults) == 2
    assert result.faults[0].ended_at == WINDOW_END
    assert result.faults[1].started_at == second


def test_the_window_covers_the_whole_period_the_receiver_was_raised() -> None:
    # spec: anom-007 -- `anom-001`'s episode is the seed and not the
    # boundary: it begins where the threshold was crossed, and the event
    # began where the receiver left its baseline.
    late = loud(
        sensor="RF-01",
        started_at=WINDOW_START + timedelta(seconds=100),
        ended_at=WINDOW_START + timedelta(seconds=150),
    )
    result = run((late,), ONE_LOUD)

    assert result.faults[0].started_at == WINDOW_START
    assert result.faults[0].ended_at == WINDOW_END


def test_the_fault_is_located_at_the_receiver() -> None:
    # spec: anom-007 -- one receiver's fault is at that receiver and
    # nowhere else; an area would claim ground nothing was observed across.
    site = LAYOUT.site("RF-01")
    result = run((loud(sensor="RF-01"),), ONE_LOUD)

    assert result.faults[0].location == Location(lat=site.lat, lon=site.lon)


# --- refusals and structure ---------------------------------------------


def test_a_quiet_run_produces_nothing_and_says_so() -> None:
    # spec: anom-007, anom-008 -- no anomalies is not the same as not
    # having looked, and this rule has nothing to look at without them.
    result = run((), None)

    assert result.faults == ()
    assert result.dismissed == ()


def test_an_anomaly_from_outside_the_layout_is_refused() -> None:
    # spec: anom-007 -- findings and layout that disagree are a caller bug.
    # Skipping the receiver would judge fewer of them than were reported,
    # without saying so.
    stray = dataclasses.replace(loud(sensor="RF-01"), cell=RfCell("RF-99", L1))

    with pytest.raises(FaultError, match="RF-99"):
        run((stray,), ONE_LOUD)


def test_a_track_observation_is_refused() -> None:
    # spec: anom-007, anom-013 -- the ordering puts this rule first because
    # it decides on the RF pattern alone. Now that it takes observations,
    # a track observation among them is refused rather than skipped, which
    # is what keeps that guarantee structural.
    track = CanonicalObservation(
        source_id="a",
        source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK,
        timestamp=WINDOW_START,
        location=Location(lat=52.0, lon=5.0),
        data_mode=DataMode.REPLAYED,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="a",
            source_type=SourceType.OPENSKY,
            data_mode=DataMode.REPLAYED,
            scenario_run_id=1,
        ),
        payload=TrackPayload(
            aircraft_id="pseudonym-1",
            altitude_m=10000.0,
            velocity_ms=250.0,
            on_ground=False,
            position_staleness_s=5.0,
            contact_staleness_s=5.0,
        ),
    )

    with pytest.raises(FaultError, match="track"):
        run((loud(sensor="RF-01"),), observations=grid(ONE_LOUD) + (track,))


def test_a_baseline_for_a_different_metric_is_refused() -> None:
    # spec: anom-007, anom-002 -- comparing a power reading against an SNR
    # baseline produces a number and no meaning. `anom-001` refuses the
    # same mismatch and this rule reads the same table.
    table = baselines(RfMetric.SNR_DB)
    mismatched = dataclasses.replace(
        table,
        baselines={
            c: dataclasses.replace(b, metric=RfMetric.POWER_DBM)
            for c, b in table.baselines.items()
        },
    )

    with pytest.raises(FaultError, match="metric"):
        run((loud(sensor="RF-01"),), ONE_LOUD, table=mismatched)


def test_a_non_positive_radius_is_refused() -> None:
    # spec: anom-007 -- a zero radius has no neighbours by construction and
    # would make every anomaly undecided rather than failing loudly.
    with pytest.raises(FaultError):
        FaultPolicy(neighbour_radius_km=0.0)


def test_a_non_positive_bar_is_refused() -> None:
    # spec: anom-007 -- a bar of zero calls every neighbour abnormal on
    # floating-point noise, so every fault becomes environmental and the
    # rule silently never fires.
    with pytest.raises(FaultError):
        FaultPolicy(nominal_within_db=0.0)


def test_the_rule_cannot_see_track_evidence() -> None:
    # spec: anom-007, anom-013 -- enforced by what it can be handed rather
    # than by remembering not to look.
    parameters = set(inspect.signature(detect_sensor_faults).parameters)
    fields = {f.name for f in dataclasses.fields(SensorFault)}
    fields |= {f.name for f in dataclasses.fields(FaultPolicy)}

    assert parameters == {"findings", "observations", "baselines", "layout", "policy"}
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
        loud(sensor="RF-01"),
        loud(sensor="RF-07"),
    )
    elevate = {
        ("RF-04", L1): STAGED_DB,
        ("RF-01", 3): STAGED_DB,
        ("RF-01", L1): STAGED_DB,
        ("RF-07", L1): STAGED_DB,
    }
    forwards = run(anomalies, elevate)
    backwards = run(tuple(reversed(anomalies)), elevate)

    assert forwards == backwards
    assert [f.sensor_id for f in forwards.faults] == ["RF-01", "RF-04", "RF-07"]


def test_a_fault_is_frozen() -> None:
    # spec: anom-007 -- a detection value object is evidence, and evidence
    # that can be edited after the fact is not evidence.
    result = run((loud(sensor="RF-01"),), ONE_LOUD)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.faults[0].sensor_id = "RF-02"  # type: ignore[misc]


def test_a_dismissal_always_carries_its_reason() -> None:
    # spec: anom-007 -- the dismissals are this rule's half of the audit
    # trail for `anom-013`: the ladder must be able to say why a zone was
    # not claimed here before offering it to the next rule.
    result = run(
        (loud(sensor="RF-01"), loud(sensor="RF-02")),
        {("RF-01", L1): STAGED_DB, ("RF-02", L1): STAGED_DB},
    )

    assert all(isinstance(d, Dismissal) and d.reason for d in result.dismissed)
    assert any("RF-02" in d.reason for d in result.dismissed if d.sensor_id == "RF-01")


def test_a_neighbour_that_reported_nothing_in_the_window_is_undecided() -> None:
    # spec: anom-007 -- a receiver present in the run but silent across
    # this window is as unmeasurable as one that never reported at all,
    # and for the same reason: there is nothing to compare.
    result = run(
        (loud(sensor="RF-01"),),
        observations=tuple(
            o
            for o in grid(ONE_LOUD)
            if o.payload.sensor_id != "RF-02"
            or not (WINDOW_START <= o.timestamp <= WINDOW_END)
        ),
    )

    assert result.faults == ()
    assert result.dismissed[0].verdict is Verdict.UNDECIDED
    assert result.dismissed[0].spatial.unjudged == ("RF-02",)


def test_an_episode_the_readings_do_not_sustain_is_undecided() -> None:
    # spec: anom-007 -- `anom-001` raises an episode on a threshold being
    # crossed. If the receiver sits at its baseline across the window that
    # episode seeds, there is no pattern to attribute, and reporting a
    # fault on it would claim a broken instrument from a single tick.
    result = run((loud(sensor="RF-01"),), None)

    assert result.faults == ()
    assert len(result.dismissed) == 1
    assert result.dismissed[0].verdict is Verdict.UNDECIDED
    assert "no pattern" in result.dismissed[0].reason


def test_a_neighbour_raised_on_another_channel_is_not_the_same_cause() -> None:
    # spec: anom-007 -- a cause that reached two receivers reached them on
    # the same part of the band. A neighbour raised somewhere else in the
    # plan is a second event, and reading it as corroboration would excuse
    # a fault by pointing at an unrelated one.
    result = run(
        (loud(sensor="RF-01", channel=0),),
        {("RF-01", 0): STAGED_DB, ("RF-02", 7): STAGED_DB},
    )

    assert [f.sensor_id for f in result.faults] == ["RF-01"]


def test_one_raised_channel_on_a_neighbour_is_enough() -> None:
    # spec: anom-007 -- the neighbour is judged on its worst channel among
    # the ones the subject was raised on, not its best. Averaging a raised
    # channel against a nominal one would hide the corroboration.
    result = run(
        (loud(sensor="RF-01", channel=3), loud(sensor="RF-01")),
        {("RF-01", 3): STAGED_DB, ("RF-01", L1): STAGED_DB, ("RF-02", L1): STAGED_DB},
    )

    assert result.faults == ()
    assert result.dismissed[0].verdict is Verdict.ENVIRONMENTAL


def test_a_single_raised_tick_does_not_make_a_neighbour_abnormal() -> None:
    # spec: anom-007 -- nominality is a question about the window, so the
    # measure is the mean across it and not the worst instant in it. On a
    # peak, one tick of ordinary noise on one neighbour would excuse every
    # fault in the layout.
    spike = WINDOW_START + timedelta(seconds=100)
    result = run(
        (loud(sensor="RF-01"),),
        observations=swap(
            grid(ONE_LOUD),
            grid({("RF-02", L1): STAGED_DB}, window=(spike, spike)),
            (("RF-02", L1),),
        ),
    )

    assert [f.sensor_id for f in result.faults] == ["RF-01"]
    assert dict(result.faults[0].spatial.elevations)["RF-02"] < 1.0
