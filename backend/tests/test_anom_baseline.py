"""The rolling-average baseline engine. Spec: anom-002.

The baseline is what every RF detector measures deviation against, so an
error here is not a wrong number in one place -- it is a wrong expectation
that every subsequent rule inherits silently.

Four groups, and the first exists because of a measurement rather than a
hunch. Against the twenty quiet runs in the development database the
fifty-six sensor-channel cells are statistically indistinguishable: cell
means span 0.177 dB and cell standard deviations run 1.437 to 1.551. A
pooled per-sensor baseline would therefore reproduce the per-cell numbers
almost exactly, so **any test of the per-channel requirement built from
quiet data cannot fail**, whatever the implementation does. The granularity
tests below are built from a constructed series in which one channel is
genuinely loud, which is the only shape that can tell the two apart. The
item was amended to say so before these were written.

Nothing here touches a database. The engine takes observations and returns
values; fetching them is the repository's job, and keeping the two apart is
what lets the arithmetic be tested without Docker.
"""

from __future__ import annotations

from collections.abc import Iterator
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
from app.detection.baseline import (
    DEFAULT_MIN_SAMPLES,
    Baseline,
    BaselineError,
    BaselineTable,
    InsufficientSamples,
    RfCell,
    RfMetric,
    compute_rf_baselines,
)

#: A quiet run id, and one that is not quiet. The engine cannot tell them
#: apart by inspection -- an observation carries no scenario type -- so the
#: caller names the quiet ones and the engine refuses everything else.
QUIET_RUN = 1
STAGED_RUN = 2

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)

#: The shipped layout's cadence and grid, from `scn-005`.
INTERVAL = timedelta(seconds=10)
CHANNELS = tuple(range(8))

#: Quiet nominal power, and a loud one. The gap is far wider than the
#: 1.5 dB spread the real quiet data shows, deliberately: these tests have
#: to separate a per-cell baseline from a pooled one, and a difference
#: inside the natural spread cannot do that.
QUIET_DBM = -95.0
LOUD_DBM = -80.0


def rf(
    *,
    sensor_id: str = "RF-01",
    channel_index: int = 0,
    power_dbm: float = QUIET_DBM,
    snr_db: float = 20.0,
    timestamp: datetime = START,
    run_id: int = QUIET_RUN,
) -> CanonicalObservation:
    """One RF reading. Only the fields the baseline reads ever vary."""
    return CanonicalObservation(
        source_id="synthetic-rf",
        source_type=SourceType.SYNTHETIC_RF,
        observation_type=ObservationType.RF,
        timestamp=timestamp,
        location=Location(lat=52.0, lon=5.0),
        data_mode=DataMode.SYNTHETIC,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="synthetic-rf",
            source_type=SourceType.SYNTHETIC_RF,
            data_mode=DataMode.SYNTHETIC,
            scenario_run_id=run_id,
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


def series(
    *,
    sensor_id: str = "RF-01",
    channel_index: int = 0,
    power_dbm: float = QUIET_DBM,
    snr_db: float = 20.0,
    count: int = DEFAULT_MIN_SAMPLES,
    run_id: int = QUIET_RUN,
    start: datetime = START,
) -> Iterator[CanonicalObservation]:
    """`count` readings on one cell, one interval apart."""
    for tick in range(count):
        yield rf(
            sensor_id=sensor_id,
            channel_index=channel_index,
            power_dbm=power_dbm,
            snr_db=snr_db,
            timestamp=start + tick * INTERVAL,
            run_id=run_id,
        )


def one_loud_channel() -> list[CanonicalObservation]:
    """A sensor whose channel 0 is loud and whose other seven are quiet.

    The shape the real quiet corpus cannot produce, and the only one that
    separates a per-channel baseline from a pooled per-sensor one.
    """
    observations: list[CanonicalObservation] = []
    for channel in CHANNELS:
        power = LOUD_DBM if channel == 0 else QUIET_DBM
        observations.extend(series(channel_index=channel, power_dbm=power))
    return observations


#: What a per-sensor pool would produce over `one_loud_channel`, and what no
#: per-cell baseline may ever equal: (7 x -95.0 + -80.0) / 8.
POOLED_DBM = (7 * QUIET_DBM + LOUD_DBM) / 8


def compute(
    observations: list[CanonicalObservation],
    *,
    metric: RfMetric = RfMetric.POWER_DBM,
    window: timedelta = timedelta(hours=1),
    ending_at: datetime | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> BaselineTable:
    """The call under test, with the arguments these tests do not vary."""
    return compute_rf_baselines(
        observations,
        metric,
        baseline_run_ids={QUIET_RUN},
        window=window,
        ending_at=ending_at,
        min_samples=min_samples,
    )


# ------------------------------------------------- per sensor per channel
#
# The item's second failure case. See the module docstring on why none of
# these is built from quiet data.


def test_a_loud_channel_does_not_move_its_quiet_neighbours() -> None:
    # spec: anom-002
    table = compute(one_loud_channel())

    for channel in CHANNELS[1:]:
        baseline = table.baselines[RfCell("RF-01", channel)]
        assert baseline.mean == pytest.approx(QUIET_DBM)


def test_no_cell_baseline_equals_the_per_sensor_pool() -> None:
    """The pooled value fits neither the loud channel nor the quiet ones.

    Asserted against the pool explicitly rather than by checking the quiet
    channels alone, because an implementation that pooled would still put a
    number in every cell -- just the wrong one, in all eight.
    """
    # spec: anom-002
    table = compute(one_loud_channel())

    for channel in CHANNELS:
        baseline = table.baselines[RfCell("RF-01", channel)]
        assert abs(baseline.mean - POOLED_DBM) > 1.0


def test_the_loud_channel_keeps_its_own_baseline() -> None:
    # spec: anom-002
    table = compute(one_loud_channel())

    assert table.baselines[RfCell("RF-01", 0)].mean == pytest.approx(LOUD_DBM)


def test_two_sensors_on_the_same_channel_are_separate_cells() -> None:
    """Per sensor as well as per channel, and the same argument applies."""
    # spec: anom-002, FR-108
    observations = [
        *series(sensor_id="RF-01", power_dbm=QUIET_DBM),
        *series(sensor_id="RF-02", power_dbm=LOUD_DBM),
    ]

    table = compute(observations)

    assert table.baselines[RfCell("RF-01", 0)].mean == pytest.approx(QUIET_DBM)
    assert table.baselines[RfCell("RF-02", 0)].mean == pytest.approx(LOUD_DBM)


def test_every_occupied_cell_gets_its_own_entry() -> None:
    # spec: anom-002, scn-005
    table = compute(one_loud_channel())

    assert set(table.baselines) == {RfCell("RF-01", channel) for channel in CHANNELS}


# --------------------------------------------------- quiet runs only
#
# The item's first failure case, and the reason the caller has to name the
# runs: an observation carries no scenario type, so the engine has no way to
# recognise staged data by inspection (`api-009`, `dal-001`).


def test_an_observation_from_an_unlisted_run_is_refused() -> None:
    # spec: anom-002, api-009
    observations = [*series(), rf(run_id=STAGED_RUN)]

    with pytest.raises(BaselineError, match=str(STAGED_RUN)):
        compute(observations)


def test_a_refused_batch_returns_nothing_at_all() -> None:
    """No partial table. A baseline computed from most of a batch is not a
    smaller correct answer, it is a wrong one that looks right."""
    # spec: anom-002
    observations = [*series(), rf(run_id=STAGED_RUN)]

    with pytest.raises(BaselineError):
        compute(observations)

    clean = compute([*series()])
    assert clean.baselines[RfCell("RF-01", 0)].mean == pytest.approx(QUIET_DBM)


def test_an_empty_set_of_baseline_runs_is_refused() -> None:
    """Naming no quiet runs cannot mean 'accept anything'."""
    # spec: anom-002
    with pytest.raises(BaselineError):
        compute_rf_baselines(
            list(series()),
            RfMetric.POWER_DBM,
            baseline_run_ids=set(),
            window=timedelta(hours=1),
        )


def test_a_track_observation_is_refused() -> None:
    """The engine is RF-only by the 2026-09-14 narrowing. A track
    observation has no sensor and no channel, so silently skipping it would
    mean a caller reading a baseline built from nothing."""
    # spec: anom-002
    track = CanonicalObservation(
        source_id="opensky",
        source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK,
        timestamp=START,
        location=Location(lat=52.0, lon=5.0),
        data_mode=DataMode.REPLAYED,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="opensky",
            source_type=SourceType.OPENSKY,
            data_mode=DataMode.REPLAYED,
            scenario_run_id=QUIET_RUN,
        ),
        payload=TrackPayload(
            aircraft_id="ac-1",
            on_ground=False,
            position_staleness_s=0.0,
            contact_staleness_s=0.0,
        ),
    )

    with pytest.raises(BaselineError):
        compute([*series(), track])


# ------------------------------------------------------ insufficient data
#
# The item's constraint that a thin window says so rather than returning an
# average that looks like every other average.


def test_a_thin_cell_reports_insufficient_samples_rather_than_a_mean() -> None:
    # spec: anom-002
    table = compute(list(series(count=DEFAULT_MIN_SAMPLES - 1)))

    cell = RfCell("RF-01", 0)
    assert cell not in table.baselines
    assert isinstance(table.insufficient[cell], InsufficientSamples)


def test_a_single_sample_never_becomes_a_baseline() -> None:
    """The item's named failure case. One reading has a standard deviation
    of zero, against which every later reading deviates infinitely."""
    # spec: anom-002
    table = compute([rf()])

    assert table.baselines == {}
    assert table.insufficient[RfCell("RF-01", 0)].samples == 1


def test_an_insufficient_result_carries_what_was_missing() -> None:
    """'Not enough' is not actionable; 'twelve of thirty' is."""
    # spec: anom-002
    table = compute(list(series(count=12)), min_samples=30)

    thin = table.insufficient[RfCell("RF-01", 0)]
    assert (thin.samples, thin.required) == (12, 30)


def test_a_minimum_below_two_is_refused() -> None:
    """A standard deviation needs two points. Accepting one would make the
    single-sample failure case reachable through configuration."""
    # spec: anom-002
    with pytest.raises(BaselineError):
        compute(list(series()), min_samples=1)


def test_thin_and_sufficient_cells_coexist() -> None:
    """One thin cell must not suppress the rest of the table."""
    # spec: anom-002
    observations = [
        *series(channel_index=0, count=DEFAULT_MIN_SAMPLES),
        *series(channel_index=1, count=2),
    ]

    table = compute(observations, min_samples=DEFAULT_MIN_SAMPLES)

    assert RfCell("RF-01", 0) in table.baselines
    assert RfCell("RF-01", 1) in table.insufficient


# ------------------------------------------------------------- the window
#
# What makes this a rolling average rather than an average.


def test_observations_before_the_window_do_not_contribute() -> None:
    # spec: anom-002, FR-302
    recent = list(series(power_dbm=QUIET_DBM, start=START))
    old = list(series(power_dbm=LOUD_DBM, start=START - timedelta(hours=6)))

    table = compute([*old, *recent], window=timedelta(minutes=30))

    assert table.baselines[RfCell("RF-01", 0)].mean == pytest.approx(QUIET_DBM)


def test_the_window_ends_at_the_newest_observation_by_default() -> None:
    """Not at the wall clock. A replayed hour from 2022 has no relationship
    to the time now, and a window anchored to `now` would be empty."""
    # spec: anom-002
    table = compute(list(series()), window=timedelta(minutes=30))

    assert table.baselines[RfCell("RF-01", 0)].samples == DEFAULT_MIN_SAMPLES


def test_the_window_end_can_be_given_explicitly() -> None:
    """Which is what makes the average roll: the same observations
    evaluated at two points give two baselines."""
    # spec: anom-002, FR-302
    early = list(series(power_dbm=LOUD_DBM, start=START))
    late = list(series(power_dbm=QUIET_DBM, start=START + timedelta(hours=2)))
    observations = [*early, *late]
    window = timedelta(minutes=30)

    at_early = compute(
        observations, window=window, ending_at=START + timedelta(minutes=10)
    )
    at_late = compute(observations, window=window)

    assert at_early.baselines[RfCell("RF-01", 0)].mean == pytest.approx(LOUD_DBM)
    assert at_late.baselines[RfCell("RF-01", 0)].mean == pytest.approx(QUIET_DBM)


def test_a_window_containing_nothing_yields_an_empty_table() -> None:
    # spec: anom-002
    table = compute(
        list(series()), window=timedelta(minutes=1), ending_at=START - timedelta(days=1)
    )

    assert table.baselines == {}
    assert table.insufficient == {}


# -------------------------------------------------------------- the value


def test_power_and_snr_are_different_baselines() -> None:
    """The metric is an input, not a fixed field."""
    # spec: anom-002, FR-303
    observations = list(series(power_dbm=QUIET_DBM, snr_db=19.0))

    power = compute(observations, metric=RfMetric.POWER_DBM)
    snr = compute(observations, metric=RfMetric.SNR_DB)

    assert power.baselines[RfCell("RF-01", 0)].mean == pytest.approx(QUIET_DBM)
    assert snr.baselines[RfCell("RF-01", 0)].mean == pytest.approx(19.0)


def test_the_baseline_carries_its_spread_and_its_sample_count() -> None:
    """`anom-003` reads the standard deviation from here; `anom-001` reads
    the mean. Both need to know how many points stand behind them."""
    # spec: anom-002, anom-003
    powers = [-96.0, -95.0, -94.0]
    observations = [
        rf(power_dbm=power, timestamp=START + index * INTERVAL)
        for index, power in enumerate(powers * 10)
    ]

    baseline = compute(observations, min_samples=2).baselines[RfCell("RF-01", 0)]

    assert isinstance(baseline, Baseline)
    assert baseline.mean == pytest.approx(-95.0)
    assert baseline.stdev == pytest.approx(0.8304547985373997, rel=1e-9)
    assert baseline.samples == 30


def test_a_flat_series_is_a_degenerate_baseline_not_an_absent_one() -> None:
    """`anom-003`'s failure case is a zero standard deviation dividing by
    zero. It can only guard against one it can see."""
    # spec: anom-002, anom-003
    baseline = compute(list(series())).baselines[RfCell("RF-01", 0)]

    assert baseline.stdev == 0.0
    assert baseline.degenerate is True


def test_a_varying_series_is_not_degenerate() -> None:
    # spec: anom-002
    observations = [
        rf(power_dbm=QUIET_DBM + (index % 2), timestamp=START + index * INTERVAL)
        for index in range(DEFAULT_MIN_SAMPLES)
    ]

    assert compute(observations).baselines[RfCell("RF-01", 0)].degenerate is False


def test_the_order_observations_arrive_in_is_not_an_input() -> None:
    """`scn-001` established this for the generator and it holds here:
    traversal order must not reach the number. A baseline that depends on
    it is not reproducible from a seed."""
    # spec: anom-002, FR-301, scn-001
    observations = one_loud_channel()

    forward = compute(observations)
    backward = compute(list(reversed(observations)))

    assert forward.baselines == backward.baselines


def test_the_table_reports_the_window_it_was_computed_over() -> None:
    """A baseline without its window is a number nobody can reproduce."""
    # spec: anom-002, NFR-601
    window = timedelta(minutes=30)

    table = compute(list(series()), window=window)

    assert table.window == window
    assert table.metric is RfMetric.POWER_DBM
    assert table.ending_at == START + (DEFAULT_MIN_SAMPLES - 1) * INTERVAL
