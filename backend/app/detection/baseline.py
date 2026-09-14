"""The rolling-average baseline engine. Spec: anom-002.

A deviation only means something against an expectation, and this is where
the expectation is built: the average, spread and sample count of a metric
over quiet runs, against which `anom-001` sets a threshold and `anom-003`
computes a z-score.

**Per sensor per channel, never pooled** (FR-108, `scn-005`). The layout is
seven sensors reporting on eight 2 MHz channels each, and pooling a sensor's
eight channels into one number means a deviation confined to one channel is
averaged against seven quiet ones. That is the discrimination `anom-007`
exists to make -- a single loud channel with clean neighbours is evidence
about the instrument, a deviation across all eight is evidence about the
environment -- so a pooled baseline would not be a coarser version of this,
it would remove the distinction the sensor-fault rule is built on.

Worth stating plainly, because it changes how this is tested: **the real
quiet data cannot demonstrate that requirement.** Measured 2026-09-14 over
the twenty completed normal-baseline runs, the fifty-six cells are
statistically indistinguishable -- cell means spanning 0.177 dB, cell
standard deviations from 1.437 to 1.551 -- because `scn-001`'s emitter gives
every cell the same nominal by construction. A pooled implementation would
reproduce the per-cell numbers almost exactly. The granularity is therefore
justified structurally rather than empirically on clean data, and its tests
are built from a constructed series in which one channel is genuinely loud.

**The engine cannot recognise staged data by looking at it.** An observation
carries no scenario type -- `api-009` forbids it, and `dal-001` gives the
model nowhere to put one -- so nothing here can tell a quiet reading from an
injected one. The caller names the runs the baseline may draw from and
anything else is refused. That turns "derives from normal-scenario data
only" from a convention into an enforced precondition, which is the only
form of it a test can hold.

Scope, narrowed 2026-09-14 and recorded on the item: RF metrics only. The
item also asks for track metrics per region, and no region concept exists
anywhere in the project while nothing consumes a track baseline. The engine
is written per *cell* so that half is a second cell extractor and a region
decision rather than a rewrite.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import NamedTuple

from app.dal.models import CanonicalObservation, RfPayload

#: Below this a mean is an anecdote. Thirty is the conventional floor for a
#: usable mean and spread, and the shipped grid produces 1,800 samples per
#: cell across the twenty quiet runs, so nothing real is near it -- the
#: value exists to catch a thin window, not to constrain the ordinary case.
DEFAULT_MIN_SAMPLES = 30

#: Two points is the arithmetic floor: a standard deviation needs a second
#: sample. Permitting one would make the item's named failure case -- a
#: single sample returned as though it were a baseline -- reachable through
#: configuration rather than through a bug.
MINIMUM_MIN_SAMPLES = 2


class BaselineError(ValueError):
    """A baseline was asked for in a way that could only mislead."""


class RfMetric(str, Enum):
    """The metrics a baseline can be built over.

    A closed set, and deliberately not every numeric field on the payload.
    `centre_frequency_mhz` and `bandwidth_mhz` are configuration read back,
    so a baseline over them would measure the layout rather than the
    environment; `baseline_delta_db` is the emitter's own idea of deviation,
    and taking it as an input would mean the detectors measure deviation
    against the generator's answer rather than against observed data.
    """

    POWER_DBM = "power_dbm"
    SNR_DB = "snr_db"


#: One reader per metric rather than `getattr` on its value, so adding a
#: member without a reader is a type error here instead of an attribute
#: error on the first batch that uses it.
_READERS: Mapping[RfMetric, Callable[[RfPayload], float]] = {
    RfMetric.POWER_DBM: lambda payload: payload.power_dbm,
    RfMetric.SNR_DB: lambda payload: payload.snr_db,
}


class RfCell(NamedTuple):
    """One sensor on one channel: the unit a baseline is computed over."""

    sensor_id: str
    channel_index: int


@dataclass(frozen=True, slots=True)
class Baseline:
    """What normal looks like in one cell, with the evidence behind it."""

    cell: RfCell
    metric: RfMetric
    mean: float
    #: Sample standard deviation, n-1. `anom-003` divides by this.
    stdev: float
    samples: int

    @property
    def degenerate(self) -> bool:
        """Every sample identical, so any deviation is infinite in z.

        Carried rather than suppressed: `anom-003`'s failure case is a
        zero standard deviation dividing by zero, and it can only guard
        against a state it is able to see.
        """
        return self.stdev == 0.0


@dataclass(frozen=True, slots=True)
class InsufficientSamples:
    """Too thin a window to call a baseline, and by how much.

    An explicit result rather than a `None` or an average over one point:
    "not enough" is not actionable, "twelve of thirty" is, and an average
    over one point is indistinguishable from a real baseline downstream.
    """

    cell: RfCell
    metric: RfMetric
    samples: int
    required: int


@dataclass(frozen=True, slots=True)
class BaselineTable:
    """Every cell's baseline, and every cell that could not have one.

    Carries the window and its end because a baseline without them is a
    number nobody can reproduce (NFR-601).
    """

    metric: RfMetric
    window: timedelta
    #: The point the trailing window ends at. `None` only when nothing was
    #: supplied and no end was given, so there was no window to evaluate.
    ending_at: datetime | None
    baselines: Mapping[RfCell, Baseline] = field(default_factory=dict)
    insufficient: Mapping[RfCell, InsufficientSamples] = field(default_factory=dict)


def compute_rf_baselines(
    observations: Iterable[CanonicalObservation],
    metric: RfMetric,
    *,
    baseline_run_ids: Collection[int],
    window: timedelta,
    ending_at: datetime | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> BaselineTable:
    """Mean, spread and sample count per sensor-channel cell.

    `baseline_run_ids` is the set of quiet runs the baseline may be built
    from; an observation from any other run raises rather than being
    skipped, because a baseline computed from most of a batch is not a
    smaller correct answer but a wrong one that looks right.

    `window` is a trailing duration and `ending_at` the point it ends at,
    defaulting to the newest observation supplied rather than to the wall
    clock -- a replayed hour from 2022 has no relationship to the time now,
    and a window anchored to `now` would be empty. Evaluating the same
    observations at two ends is what makes the average roll.
    """
    if not baseline_run_ids:
        raise BaselineError(
            "no baseline runs named. An empty set cannot mean 'accept "
            "anything': the engine has no way to recognise staged data by "
            "inspection, because an observation carries no scenario type."
        )
    if min_samples < MINIMUM_MIN_SAMPLES:
        raise BaselineError(
            f"min_samples={min_samples} is below {MINIMUM_MIN_SAMPLES}: a "
            "standard deviation needs two points, and one sample returned as "
            "a baseline is the failure case this argument would reopen."
        )
    if window <= timedelta(0):
        raise BaselineError(f"window={window!r} must be a positive duration")

    allowed = frozenset(baseline_run_ids)
    read = _READERS[metric]

    # Validated in full before anything is measured, so a batch carrying one
    # staged observation yields no table at all rather than a partial one.
    readings: list[tuple[RfCell, datetime, float]] = []
    for observation in observations:
        run_id = observation.provenance.scenario_run_id
        if run_id not in allowed:
            raise BaselineError(
                f"observation from scenario run {run_id}, which is not one of "
                f"the baseline runs {sorted(allowed)}. A baseline built over "
                "injected data is an expectation that already contains the "
                "deviation it exists to measure."
            )
        payload = observation.payload
        if not isinstance(payload, RfPayload):
            raise BaselineError(
                f"{observation.observation_type.value} observation has no "
                "sensor and no channel, so it belongs to no cell. Skipping it "
                "would hand back a baseline built from fewer readings than the "
                "caller supplied, without saying so."
            )
        readings.append(
            (
                RfCell(payload.sensor_id, payload.channel_index),
                observation.timestamp,
                read(payload),
            )
        )

    end = ending_at if ending_at is not None else _newest(readings)
    if end is None:
        return BaselineTable(metric=metric, window=window, ending_at=None)

    start = end - window
    per_cell: dict[RfCell, list[float]] = {}
    for cell, timestamp, value in readings:
        if start <= timestamp <= end:
            per_cell.setdefault(cell, []).append(value)

    baselines: dict[RfCell, Baseline] = {}
    insufficient: dict[RfCell, InsufficientSamples] = {}
    for cell, values in per_cell.items():
        if len(values) < min_samples:
            insufficient[cell] = InsufficientSamples(
                cell=cell,
                metric=metric,
                samples=len(values),
                required=min_samples,
            )
            continue
        # `statistics.mean` and `stdev` sum exactly rather than in float, so
        # the result does not depend on the order the readings arrived in.
        # `scn-001` established that traversal order must never reach a
        # number a run has to be reproducible from.
        baselines[cell] = Baseline(
            cell=cell,
            metric=metric,
            mean=statistics.mean(values),
            stdev=statistics.stdev(values),
            samples=len(values),
        )

    return BaselineTable(
        metric=metric,
        window=window,
        ending_at=end,
        baselines=baselines,
        insufficient=insufficient,
    )


def _newest(readings: list[tuple[RfCell, datetime, float]]) -> datetime | None:
    return max((timestamp for _, timestamp, _ in readings), default=None)
