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
    findings = detect_rf_noise(run_of([JUST_OVER]), baseline_of(CELL), POLICY)

    assert len(findings.anomalies) == 1


def test_the_threshold_comes_from_the_policy_and_not_from_the_rule() -> None:
    """Same readings, two thresholds, two answers. The item's first
    constraint is that the threshold is configuration."""
    # spec: anom-001
    readings = run_of([JUST_OVER])
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
            run_of([JUST_OVER]),
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
    (anomaly,) = detect_rf_noise(run_of([power]), baseline_of(CELL), POLICY).anomalies

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
        run_of([HIGH_POWER]), baseline_of(CELL), POLICY
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
        run_of([JUST_OVER]), baseline_of(CELL), POLICY
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
        detect_rf_noise([*run_of([JUST_OVER]), track], baseline_of(CELL), POLICY)


def test_the_order_readings_arrive_in_is_not_an_input() -> None:
    """`scn-001` for the generator, `anom-002` for the baseline, and the
    same requirement here: a finding that depends on traversal order is not
    reproducible from a seed."""
    # spec: anom-001, FR-301, NFR-601
    powers = [QUIET_DBM, JUST_OVER, HIGH_POWER, QUIET_DBM, MEDIUM_POWER]
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
        run_of([JUST_OVER]), baseline_of(CELL), POLICY
    ).anomalies

    assert isinstance(anomaly, RfNoiseAnomaly)
    with pytest.raises(Exception):
        anomaly.severity = Severity.HIGH  # type: ignore[misc]
