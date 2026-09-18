"""The RF threshold rule, `RF-NOISE`. Spec: anom-001.

The first rule in the project that raises an anomaly, and therefore the
first code that makes a claim about the world rather than moving data.

Five groups. The boundary group is the item's own failure case made exact
-- at the baseline, at the threshold, and one unit past it -- and the
direction group exists because the naive form of this rule is wrong in a
way that reads as correct: an absolute deviation reports a channel quieter
than its baseline as noise, when a quiet channel is a different fault and
probably a dead receiver.

The last group is `anom-008` in miniature. A detector that skipped what it
could not measure would let "zero anomalies on a clean run" be satisfied by
not having looked, so a cell with no usable baseline is reported unjudged
rather than counted clean.

Baselines are constructed directly rather than computed, so the threshold
arithmetic is legible at the point of assertion. One test goes through the
real engine end to end, to prove the two halves fit.
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
    ValidationStatus,
)
from app.detection.baseline import (
    Baseline,
    BaselineTable,
    InsufficientSamples,
    RfCell,
    RfMetric,
    compute_rf_baselines,
)
from app.detection.rf_noise import (
    ANOMALY_TYPE,
    DEFAULT_MINIMUM_DURATION,
    RULE_ID,
    Direction,
    RfNoiseAnomaly,
    RuleError,
    Severity,
    ThresholdPolicy,
    detect_rf_noise,
)

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
INTERVAL = timedelta(seconds=10)

#: The quiet nominal the emitter produces, and the sensor that reports it.
QUIET_DBM = -95.0
SENSOR = "RF-01"
CELL = RfCell(SENSOR, 0)
SITE = Location(lat=52.3, lon=4.76)

#: Trigger 6 dB past the baseline, Medium at 10, High at 15. Configuration,
#: not literals in the rule -- these values are the item's first constraint.
POLICY = ThresholdPolicy(
    metric=RfMetric.POWER_DBM,
    direction=Direction.ABOVE,
    threshold=6.0,
    medium_at=10.0,
    high_at=15.0,
)

AT_THRESHOLD = QUIET_DBM + 6.0  # -89.0, must raise nothing
JUST_OVER = QUIET_DBM + 7.0  # -88.0, must raise exactly one
MEDIUM_POWER = QUIET_DBM + 11.0
HIGH_POWER = QUIET_DBM + 16.0


def rf(
    *,
    power_dbm: float = QUIET_DBM,
    snr_db: float = 20.0,
    sensor_id: str = SENSOR,
    channel_index: int = 0,
    timestamp: datetime = START,
    location: Location = SITE,
) -> CanonicalObservation:
    return CanonicalObservation(
        source_id="synthetic-rf",
        source_type=SourceType.SYNTHETIC_RF,
        observation_type=ObservationType.RF,
        timestamp=timestamp,
        location=location,
        data_mode=DataMode.SYNTHETIC,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="synthetic-rf",
            source_type=SourceType.SYNTHETIC_RF,
            data_mode=DataMode.SYNTHETIC,
            scenario_run_id=1,
        ),
        payload=RfPayload(
            sensor_id=sensor_id,
            channel_index=channel_index,
            centre_frequency_mhz=1567.42 + 2.0 * channel_index,
            band="GNSS-L1",
            power_dbm=power_dbm,
            snr_db=snr_db,
            bandwidth_mhz=2.0,
            signal_type="noise",
            baseline_delta_db=0.0,
        ),
    )


def run_of(
    powers: list[float], *, channel_index: int = 0
) -> list[CanonicalObservation]:
    """One reading per interval in one cell, in the order given."""
    return [
        rf(power_dbm=power, channel_index=channel_index, timestamp=START + i * INTERVAL)
        for i, power in enumerate(powers)
    ]


def baseline_of(
    *cells: RfCell,
    mean: float = QUIET_DBM,
    stdev: float = 1.5,
    metric: RfMetric = RfMetric.POWER_DBM,
) -> BaselineTable:
    return BaselineTable(
        metric=metric,
        window=timedelta(hours=1),
        ending_at=START,
        baselines={
            cell: Baseline(
                cell=cell, metric=metric, mean=mean, stdev=stdev, samples=1800
            )
            for cell in cells
        },
    )


# ------------------------------------------------------------- the boundary


def test_readings_at_the_baseline_raise_nothing() -> None:
    """The item's first named failure case."""
    # spec: anom-001
    findings = detect_rf_noise(run_of([QUIET_DBM] * 5), baseline_of(CELL), POLICY)

    assert findings.anomalies == ()


def test_a_reading_exactly_at_the_threshold_raises_nothing() -> None:
    """Strictly greater than. The threshold is the limit of acceptable, so
    a reading sitting on it has not passed it."""
    # spec: anom-001
    findings = detect_rf_noise(run_of([AT_THRESHOLD] * 5), baseline_of(CELL), POLICY)

    assert findings.anomalies == ()


def test_a_reading_one_unit_past_the_threshold_raises_exactly_one() -> None:
    """The item's second named failure case."""
    # spec: anom-001, FR-303
    findings = detect_rf_noise(run_of([JUST_OVER] * 2), baseline_of(CELL), POLICY)

    assert len(findings.anomalies) == 1


def test_the_threshold_comes_from_the_policy_and_not_from_the_rule() -> None:
    """Same readings, two thresholds, two answers. The item's first
    constraint is that the threshold is configuration."""
    # spec: anom-001
    readings = run_of([JUST_OVER] * 2)
    permissive = ThresholdPolicy(
        metric=RfMetric.POWER_DBM,
        direction=Direction.ABOVE,
        threshold=20.0,
        medium_at=25.0,
        high_at=30.0,
    )

    assert detect_rf_noise(readings, baseline_of(CELL), POLICY).anomalies != ()
    assert detect_rf_noise(readings, baseline_of(CELL), permissive).anomalies == ()


# ------------------------------------------------------------- the direction


def test_a_channel_quieter_than_its_baseline_is_not_noise() -> None:
    """The rule's most plausible wrong implementation. An absolute
    deviation reports this as interference; it is a different fault, and
    probably a dead receiver."""
    # spec: anom-001
    findings = detect_rf_noise(
        run_of([QUIET_DBM - 12.0] * 5), baseline_of(CELL), POLICY
    )

    assert findings.anomalies == ()


def test_snr_is_measured_downwards() -> None:
    """Noise rising is what drives SNR down, so the same event appears as a
    fall on this metric and a rise on power."""
    # spec: anom-001, FR-303
    policy = ThresholdPolicy(
        metric=RfMetric.SNR_DB,
        direction=Direction.BELOW,
        threshold=6.0,
        medium_at=10.0,
        high_at=15.0,
    )
    baselines = baseline_of(CELL, mean=20.0, metric=RfMetric.SNR_DB)
    degraded = [rf(snr_db=13.0, timestamp=START + i * INTERVAL) for i in range(3)]
    improved = [rf(snr_db=27.0, timestamp=START + i * INTERVAL) for i in range(3)]

    assert detect_rf_noise(degraded, baselines, policy).anomalies != ()
    assert detect_rf_noise(improved, baselines, policy).anomalies == ()


def test_a_policy_and_a_baseline_for_different_metrics_are_refused() -> None:
    """Comparing a power reading against an SNR baseline produces a number
    and no meaning at all."""
    # spec: anom-001
    with pytest.raises(RuleError, match="metric"):
        detect_rf_noise(
            run_of([JUST_OVER] * 2),
            baseline_of(CELL, mean=20.0, metric=RfMetric.SNR_DB),
            POLICY,
        )


# --------------------------------------------------------------- episodes


def test_consecutive_exceeding_readings_are_one_anomaly() -> None:
    """Not one per reading. A run emits 5,040 readings, so per-reading
    anomalies would describe one event thousands of times."""
    # spec: anom-001, evb-001
    findings = detect_rf_noise(run_of([JUST_OVER] * 6), baseline_of(CELL), POLICY)

    assert len(findings.anomalies) == 1


def test_an_episode_spans_its_first_and_last_exceeding_reading() -> None:
    # spec: anom-001
    powers = [QUIET_DBM, JUST_OVER, JUST_OVER, JUST_OVER, QUIET_DBM]

    (anomaly,) = detect_rf_noise(run_of(powers), baseline_of(CELL), POLICY).anomalies

    assert anomaly.started_at == START + 1 * INTERVAL
    assert anomaly.ended_at == START + 3 * INTERVAL


def test_a_quiet_reading_between_two_loud_ones_splits_the_episode() -> None:
    """Otherwise two separate events an hour apart become one anomaly
    claiming to span the quiet hour between them."""
    # spec: anom-001
    powers = [JUST_OVER, JUST_OVER, QUIET_DBM, JUST_OVER, JUST_OVER]

    findings = detect_rf_noise(run_of(powers), baseline_of(CELL), POLICY)

    assert len(findings.anomalies) == 2


def test_the_anomaly_names_every_reading_that_triggered_it() -> None:
    """By natural key, which is what an analyst can look up and check."""
    # spec: anom-001, evb-002
    powers = [QUIET_DBM, JUST_OVER, JUST_OVER]

    (anomaly,) = detect_rf_noise(run_of(powers), baseline_of(CELL), POLICY).anomalies

    assert [
        (ref.sensor_id, ref.channel_index, ref.timestamp) for ref in anomaly.triggering
    ] == [
        (SENSOR, 0, START + 1 * INTERVAL),
        (SENSOR, 0, START + 2 * INTERVAL),
    ]


def test_two_cells_exceeding_are_two_anomalies() -> None:
    """Grouping across cells is evb-001's job on three axes, not this
    rule's. A rule that grouped here would pre-empt it."""
    # spec: anom-001, evb-001
    other = RfCell(SENSOR, 1)
    readings = [*run_of([JUST_OVER] * 3), *run_of([JUST_OVER] * 3, channel_index=1)]

    findings = detect_rf_noise(readings, baseline_of(CELL, other), POLICY)

    assert {anomaly.cell for anomaly in findings.anomalies} == {CELL, other}


# --------------------------------------------------------------- severity


@pytest.mark.parametrize(
    ("power", "expected"),
    [
        (JUST_OVER, Severity.LOW),
        (MEDIUM_POWER, Severity.MEDIUM),
        (HIGH_POWER, Severity.HIGH),
    ],
)
def test_severity_comes_from_the_configured_bands(
    power: float, expected: Severity
) -> None:
    # spec: anom-001, ui-001
    findings = detect_rf_noise(run_of([power] * 2), baseline_of(CELL), POLICY)
    (anomaly,) = findings.anomalies

    assert anomaly.severity is expected


def test_an_episode_takes_the_severity_of_its_worst_reading() -> None:
    """Not its first. An event that escalates is a High that began Low, and
    reporting the Low would understate it."""
    # spec: anom-001
    powers = [JUST_OVER, MEDIUM_POWER, HIGH_POWER]

    (anomaly,) = detect_rf_noise(run_of(powers), baseline_of(CELL), POLICY).anomalies

    assert anomaly.severity is Severity.HIGH


def test_the_measured_deviation_is_carried_but_severity_stays_a_word() -> None:
    """`ui-001`: never a decimal score on screen. The magnitude is kept for
    traceability, in the same arrangement anom-003 makes for its z."""
    # spec: anom-001, ui-001
    (anomaly,) = detect_rf_noise(
        run_of([HIGH_POWER] * 2), baseline_of(CELL), POLICY
    ).anomalies

    assert anomaly.peak_deviation == pytest.approx(16.0)
    assert isinstance(anomaly.severity, Severity)


def test_bands_out_of_order_are_refused() -> None:
    """A Medium band below the threshold would make every anomaly Medium,
    and a High below Medium would make the ordering meaningless."""
    # spec: anom-001
    with pytest.raises(RuleError):
        ThresholdPolicy(
            metric=RfMetric.POWER_DBM,
            direction=Direction.ABOVE,
            threshold=6.0,
            medium_at=4.0,
            high_at=15.0,
        )
    with pytest.raises(RuleError):
        ThresholdPolicy(
            metric=RfMetric.POWER_DBM,
            direction=Direction.ABOVE,
            threshold=6.0,
            medium_at=10.0,
            high_at=8.0,
        )


# ------------------------------------------------------- cells it cannot judge


def test_a_cell_with_an_insufficient_baseline_is_unjudged_not_clean() -> None:
    """The anom-008 argument. A detector that silently skips what it cannot
    measure lets 'zero anomalies' be satisfied by not having looked."""
    # spec: anom-001, anom-008
    thin = BaselineTable(
        metric=RfMetric.POWER_DBM,
        window=timedelta(hours=1),
        ending_at=START,
        insufficient={
            CELL: InsufficientSamples(
                cell=CELL, metric=RfMetric.POWER_DBM, samples=4, required=30
            )
        },
    )

    findings = detect_rf_noise(run_of([HIGH_POWER] * 3), thin, POLICY)

    assert findings.anomalies == ()
    assert [cell.cell for cell in findings.unjudged] == [CELL]


def test_a_cell_absent_from_the_baseline_table_is_unjudged() -> None:
    """Absent and insufficient are different causes with the same
    consequence: there is nothing to measure against."""
    # spec: anom-001, anom-008
    findings = detect_rf_noise(
        run_of([HIGH_POWER] * 3), baseline_of(RfCell(SENSOR, 7)), POLICY
    )

    assert findings.anomalies == ()
    assert [cell.cell for cell in findings.unjudged] == [CELL]


def test_a_judged_cell_is_not_reported_unjudged() -> None:
    # spec: anom-001
    findings = detect_rf_noise(run_of([JUST_OVER] * 3), baseline_of(CELL), POLICY)

    assert findings.unjudged == ()


def test_a_degenerate_baseline_is_still_judged() -> None:
    """This rule reads the mean and never the spread, so a zero-spread
    baseline is usable here even though it is the failure case anom-003
    has to guard against."""
    # spec: anom-001, anom-002, anom-003
    findings = detect_rf_noise(
        run_of([JUST_OVER] * 3), baseline_of(CELL, stdev=0.0), POLICY
    )

    assert len(findings.anomalies) == 1
    assert findings.unjudged == ()


# ------------------------------------------------------------ what it emits


def test_the_anomaly_carries_the_type_and_rule_the_spec_names() -> None:
    """The rule ID travels with the anomaly into the bundle, and is what
    makes an explanation checkable."""
    # spec: anom-001, FR-402
    (anomaly,) = detect_rf_noise(
        run_of([JUST_OVER] * 2), baseline_of(CELL), POLICY
    ).anomalies

    assert (anomaly.anomaly_type, anomaly.rule_id) == (ANOMALY_TYPE, RULE_ID)
    assert (ANOMALY_TYPE, RULE_ID) == ("rf_noise_deviation", "RF-NOISE")


def test_the_affected_area_is_the_reporting_sensor_position() -> None:
    """A point, not a region. An area needs corroboration from more than
    one sensor, which is anom-004 and anom-005."""
    # spec: anom-001, dal-001
    elsewhere = Location(lat=50.05, lon=8.57)
    readings = [
        rf(power_dbm=JUST_OVER, timestamp=START, location=elsewhere),
        rf(power_dbm=JUST_OVER, timestamp=START + INTERVAL, location=elsewhere),
    ]

    (anomaly,) = detect_rf_noise(readings, baseline_of(CELL), POLICY).anomalies

    assert anomaly.location == elsewhere


def test_a_track_observation_is_refused() -> None:
    """The same argument as the baseline engine: a track reading belongs to
    no cell, so skipping it would judge fewer readings than were supplied
    without saying so."""
    # spec: anom-001
    from app.dal.models import TrackPayload

    track = CanonicalObservation(
        source_id="opensky",
        source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK,
        timestamp=START,
        location=SITE,
        data_mode=DataMode.REPLAYED,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="opensky",
            source_type=SourceType.OPENSKY,
            data_mode=DataMode.REPLAYED,
            scenario_run_id=1,
        ),
        payload=TrackPayload(
            aircraft_id="ac-1",
            on_ground=False,
            position_staleness_s=0.0,
            contact_staleness_s=0.0,
        ),
    )

    with pytest.raises(RuleError):
        detect_rf_noise([*run_of([JUST_OVER] * 2), track], baseline_of(CELL), POLICY)


def test_the_order_readings_arrive_in_is_not_an_input() -> None:
    """`scn-001` for the generator, `anom-002` for the baseline, and the
    same requirement here: a finding that depends on traversal order is not
    reproducible from a seed."""
    # spec: anom-001, FR-301, NFR-601
    # Each episode is two readings long, so both clear the shipped minimum
    # duration (`anom-014`) and the cell ordering is still what is under test.
    powers = [QUIET_DBM, JUST_OVER, HIGH_POWER, QUIET_DBM, MEDIUM_POWER, MEDIUM_POWER]
    other = RfCell(SENSOR, 3)
    # Two cells, because with one there is no cell ordering to get wrong --
    # found by mutation: emitting cells in arrival order passed a
    # single-cell version of this test.
    readings = [*run_of(powers), *run_of(powers, channel_index=3)]
    baselines = baseline_of(CELL, other)

    forward = detect_rf_noise(readings, baselines, POLICY)
    backward = detect_rf_noise(list(reversed(readings)), baselines, POLICY)

    assert forward == backward
    assert [anomaly.cell for anomaly in forward.anomalies] == [
        CELL,
        CELL,
        other,
        other,
    ]


def test_a_quiet_run_against_its_own_baseline_raises_nothing() -> None:
    """Correct non-detection, through the real baseline engine rather than
    a constructed table -- the two halves have to fit. `anom-008` will
    assert this across every detector; this is its instance for this rule."""
    # spec: anom-001, anom-008, anom-002
    quiet = [
        rf(power_dbm=QUIET_DBM + (i % 3) * 0.5, timestamp=START + i * INTERVAL)
        for i in range(40)
    ]
    baselines = compute_rf_baselines(
        quiet,
        RfMetric.POWER_DBM,
        baseline_run_ids={1},
        window=timedelta(hours=1),
    )

    findings = detect_rf_noise(quiet, baselines, POLICY)

    assert findings.anomalies == ()
    assert findings.unjudged == ()


def test_an_anomaly_is_immutable() -> None:
    """A finding that passed a rule must not be editable past it, which is
    dal-001's argument applied one layer along."""
    # spec: anom-001
    (anomaly,) = detect_rf_noise(
        run_of([JUST_OVER] * 2), baseline_of(CELL), POLICY
    ).anomalies

    assert isinstance(anomaly, RfNoiseAnomaly)
    with pytest.raises(Exception):
        anomaly.severity = Severity.HIGH  # type: ignore[misc]


# ---------------------------------------------------------------------------
# anom-014: a threshold crossing that lasts one reading is not an event.
#
# anom-001 raises at least one episode on 14 of 100 runs that stage nothing
# on the RF grid, and a single-reading episode has a start equal to its end
# -- a window of no length, which anom-012 divides by. The minimum removes
# the cause rather than the symptom.
#
# Two things these tests fix and the measurement does not. A suppressed
# episode is *reported*, in its own field rather than among the unjudged
# cells: "I looked and it was too brief" is a different claim from "I had no
# baseline, so I did not look", and only the first has a window worth
# carrying. And the boundary belongs to the configured value -- an episode
# exactly at the minimum is kept -- which is the item's own failure case.
#
# The value of the minimum is not asserted here. It is measured by
# backend/measurements/corpus/rf_noise_episode_duration.py and recorded on
# the constant; these tests would pass at any minimum, which is what makes
# them tests of the mechanism rather than of the number.
# ---------------------------------------------------------------------------


def policy_with(minimum_s: float) -> ThresholdPolicy:
    """The shipped policy, with only the minimum duration changed."""
    return ThresholdPolicy(
        metric=RfMetric.POWER_DBM,
        direction=Direction.ABOVE,
        threshold=6.0,
        medium_at=10.0,
        high_at=15.0,
        minimum_duration=timedelta(seconds=minimum_s),
    )


def test_an_episode_shorter_than_the_minimum_raises_no_anomaly() -> None:
    # spec: anom-014
    # Two readings, 10 s apart, against a 30 s minimum.
    observations = run_of([QUIET_DBM, JUST_OVER, JUST_OVER, QUIET_DBM])
    found = detect_rf_noise(observations, baseline_of(CELL), policy_with(30))
    assert found.anomalies == ()


def test_a_suppressed_episode_is_reported_rather_than_dropped() -> None:
    # spec: anom-014, anom-008
    # Silently dropping it would reopen the hole anom-008 exists to close:
    # "zero anomalies" satisfied by not having said what was discarded.
    observations = run_of([QUIET_DBM, JUST_OVER, JUST_OVER, QUIET_DBM])
    found = detect_rf_noise(observations, baseline_of(CELL), policy_with(30))
    assert len(found.suppressed) == 1
    suppressed = found.suppressed[0]
    assert suppressed.cell == CELL
    assert suppressed.started_at == START + INTERVAL
    assert suppressed.ended_at == START + 2 * INTERVAL
    assert suppressed.readings == 2
    assert suppressed.minimum == timedelta(seconds=30)


def test_an_episode_exactly_at_the_minimum_is_kept() -> None:
    # spec: anom-014
    # The item's own failure case: the boundary belongs to the configured
    # value, not to the comparison. Four readings 10 s apart span 30 s.
    observations = run_of([JUST_OVER, JUST_OVER, JUST_OVER, JUST_OVER])
    found = detect_rf_noise(observations, baseline_of(CELL), policy_with(30))
    assert len(found.anomalies) == 1
    assert found.anomalies[0].ended_at - found.anomalies[0].started_at == timedelta(
        seconds=30
    )
    assert found.suppressed == ()


def test_an_episode_past_the_minimum_is_kept_and_not_reported_suppressed() -> None:
    # spec: anom-014
    observations = run_of([JUST_OVER] * 6)
    found = detect_rf_noise(observations, baseline_of(CELL), policy_with(30))
    assert len(found.anomalies) == 1
    assert found.suppressed == ()


def test_a_single_reading_episode_is_suppressed() -> None:
    # spec: anom-014, anom-012
    # The zero-length window measure_rate_excess divided by: 6 of 86 staged
    # runs produced one. anom-012 refuses it downstream; this removes it.
    observations = run_of([QUIET_DBM, JUST_OVER, QUIET_DBM])
    found = detect_rf_noise(observations, baseline_of(CELL), policy_with(10))
    assert found.anomalies == ()
    assert len(found.suppressed) == 1
    assert found.suppressed[0].started_at == found.suppressed[0].ended_at
    assert found.suppressed[0].readings == 1


def test_a_minimum_of_zero_keeps_a_single_reading_episode() -> None:
    # spec: anom-014
    # The pre-anom-014 behaviour stays representable, and therefore testable.
    observations = run_of([QUIET_DBM, JUST_OVER, QUIET_DBM])
    found = detect_rf_noise(observations, baseline_of(CELL), policy_with(0))
    assert len(found.anomalies) == 1
    assert found.suppressed == ()


def test_the_minimum_is_configuration_and_changes_the_answer() -> None:
    # spec: anom-014
    # The same readings, two policies: a number in the rule could not do this.
    observations = run_of([QUIET_DBM, JUST_OVER, JUST_OVER, JUST_OVER, QUIET_DBM])
    baselines = baseline_of(CELL)
    assert len(detect_rf_noise(observations, baselines, policy_with(20)).anomalies) == 1
    assert detect_rf_noise(observations, baselines, policy_with(30)).anomalies == ()


def test_suppression_is_per_episode_and_not_per_cell() -> None:
    # spec: anom-014
    # One cell, one brief crossing and one sustained one. Suppressing the
    # cell rather than the episode would lose the real event with the blip.
    observations = run_of(
        [JUST_OVER, QUIET_DBM, JUST_OVER, JUST_OVER, JUST_OVER, JUST_OVER]
    )
    found = detect_rf_noise(observations, baseline_of(CELL), policy_with(20))
    assert len(found.anomalies) == 1
    assert len(found.suppressed) == 1
    assert found.anomalies[0].started_at == START + 2 * INTERVAL
    assert found.suppressed[0].started_at == START


def test_a_negative_minimum_is_refused() -> None:
    # spec: anom-014
    # Refused rather than clamped: a configuration error must not become a
    # rule that has quietly stopped suppressing anything.
    with pytest.raises(RuleError, match="minimum duration"):
        ThresholdPolicy(
            metric=RfMetric.POWER_DBM,
            direction=Direction.ABOVE,
            threshold=6.0,
            medium_at=10.0,
            high_at=15.0,
            minimum_duration=timedelta(seconds=-1),
        )


def test_suppressed_episodes_come_back_in_a_stable_order() -> None:
    # spec: anom-014, NFR-601
    # Two cells, each with a brief crossing. The order must be the cells'
    # order and not the order the readings happened to arrive in.
    first = run_of([QUIET_DBM, JUST_OVER, QUIET_DBM], channel_index=0)
    second = run_of([QUIET_DBM, JUST_OVER, QUIET_DBM], channel_index=1)
    baselines = baseline_of(RfCell(SENSOR, 0), RfCell(SENSOR, 1))
    forwards = detect_rf_noise(first + second, baselines, policy_with(10))
    backwards = detect_rf_noise(second + first, baselines, policy_with(10))
    assert [s.cell for s in forwards.suppressed] == [
        RfCell(SENSOR, 0),
        RfCell(SENSOR, 1),
    ]
    assert forwards.suppressed == backwards.suppressed


def test_a_suppressed_episode_does_not_disturb_an_unjudged_cell() -> None:
    # spec: anom-014, anom-001
    # The two reports are different claims and stay in different fields.
    observations = run_of([QUIET_DBM, JUST_OVER, QUIET_DBM]) + run_of(
        [QUIET_DBM], channel_index=7
    )
    found = detect_rf_noise(observations, baseline_of(CELL), policy_with(10))
    assert len(found.suppressed) == 1
    assert [u.cell for u in found.unjudged] == [RfCell(SENSOR, 7)]


def test_the_shipped_minimum_is_one_reading_interval() -> None:
    # spec: anom-014
    # Pinned because the number is measured and a change to it must be a
    # deliberate act with a new measurement behind it, not a silent edit.
    # Over 240 stored runs every one of the 80 episodes falling outside a
    # staged cell or window was exactly one reading long, so 10 s removes
    # all 80 while still catching 140 of 140 runs that stage any RF.
    assert DEFAULT_MINIMUM_DURATION == timedelta(seconds=10)

    # And the default is what an unconfigured policy actually gets. Without
    # this the constant could be correct and unused.
    assert POLICY.minimum_duration == DEFAULT_MINIMUM_DURATION
    observations = run_of([QUIET_DBM, JUST_OVER, QUIET_DBM])
    assert detect_rf_noise(observations, baseline_of(CELL), POLICY).anomalies == ()
