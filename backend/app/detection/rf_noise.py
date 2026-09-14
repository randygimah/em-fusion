"""The RF threshold rule, `RF-NOISE`. Spec: anom-001.

The first rule in the project that raises an anomaly, and so the first code
that makes a claim about the world rather than moving data from one shape to
another. A reading is compared against what `anom-002` measured as normal
for that exact sensor and channel, and a reading far enough the wrong way
raises a finding carrying the rule that produced it.

Four things about the shape of it are decisions rather than details.

**The comparison has a direction.** Raised power is the noise signature;
falling SNR is the same event seen from the other side, because noise rising
is what drives SNR down. The obvious implementation -- an absolute deviation
past a threshold -- reports a channel *quieter* than its baseline as noise,
which is a different fault and probably a dead receiver. It would also be
invisible in testing against staged data, because staged interference only
ever pushes the metric one way.

**The unit of output is an episode, not a reading.** A run emits 5,040
readings; per-reading anomalies would describe one event thousands of times
and leave `evb-001` repairing this rule's damage instead of doing its own
grouping. A non-exceeding reading between two exceeding ones ends the
episode, so two events an hour apart do not become one anomaly claiming to
span the quiet hour between them.

**A cell with no usable baseline is reported, not skipped.** This matters to
`anom-008` more than here: a detector that silently passes over what it
cannot measure would let "zero anomalies on a clean run" be satisfied by not
having looked, and every false-positive rate computed from that would be
meaningless.

**The affected area is a point.** A single sensor reporting noise locates the
finding at that sensor and nowhere else; an *area* needs corroboration from
more than one, which is `anom-004`'s clustering and `anom-005`'s fusion.
Following `dal-001`, no geometry type appears here -- coordinates only.

Severity is Low, Medium or High and never a number on screen (`ui-001`). The
measured deviation is carried for traceability, in the same arrangement
`anom-003` makes for its z value.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.dal.models import CanonicalObservation, Location, RfPayload
from app.detection.baseline import BaselineTable, RfCell, RfMetric

#: Travels with every anomaly this rule raises, into the evidence bundle and
#: from there into the explanation an analyst reads (FR-402). The rule ID is
#: what makes a claim checkable rather than merely stated.
RULE_ID = "RF-NOISE"

#: The anomaly's own type, distinct from the rule that produced it: a later
#: rule could raise the same type from different evidence.
ANOMALY_TYPE = "rf_noise_deviation"


class RuleError(ValueError):
    """The rule was asked for something it could only answer misleadingly."""


class Direction(str, Enum):
    """Which way past the baseline counts as a deviation for this metric."""

    ABOVE = "above"
    BELOW = "below"


class Severity(str, Enum):
    """Low, Medium, High -- never a percentage and never a decimal.

    `ui-001` fixes this for anything shown to an analyst, and the enum is
    what makes anything else unrepresentable rather than merely rejected.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ThresholdPolicy:
    """What counts as a deviation, and how bad. Configuration, not literals.

    `threshold`, `medium_at` and `high_at` are deviations from the baseline
    mean in the metric's own units -- dB for power, dB for SNR -- and
    deliberately not multiples of the baseline's standard deviation. That is
    `anom-003`, and keeping the two rules apart is what makes them
    independent evidence about one reading rather than one detector counted
    twice in a bundle.
    """

    metric: RfMetric
    direction: Direction
    threshold: float
    medium_at: float
    high_at: float

    def __post_init__(self) -> None:
        if not self.threshold < self.medium_at < self.high_at:
            raise RuleError(
                f"bands must increase past the threshold, got threshold="
                f"{self.threshold}, medium_at={self.medium_at}, "
                f"high_at={self.high_at}. A Medium band at or below the "
                "threshold makes every anomaly Medium; a High below Medium "
                "makes the ordering meaningless."
            )

    def severity_for(self, deviation: float) -> Severity:
        if deviation >= self.high_at:
            return Severity.HIGH
        if deviation >= self.medium_at:
            return Severity.MEDIUM
        return Severity.LOW


@dataclass(frozen=True, slots=True)
class ReadingRef:
    """One reading, named the way a person can look it up.

    Sensor, channel and instant, rather than a database id. The canonical
    observation has no id -- `dal-001` keeps storage identity off the model
    -- and `scn-005`'s grid is dense enough that these three values name
    exactly one reading. It is also the better artefact for this phase:
    "RF-03, channel 4, at 12:07:30" is a reference an analyst can check, and
    a bigint is not. `evb-002` resolves it against the store.
    """

    sensor_id: str
    channel_index: int
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class RfNoiseAnomaly:
    """One episode of one cell reading past its threshold."""

    cell: RfCell
    metric: RfMetric
    severity: Severity
    started_at: datetime
    ended_at: datetime
    #: Where the reporting sensor stands. A point -- see the module
    #: docstring on why this rule does not produce an area.
    location: Location
    #: The worst deviation in the episode, in the metric's units. Carried
    #: for traceability and never rendered as a score (`ui-001`).
    peak_deviation: float
    triggering: tuple[ReadingRef, ...]
    anomaly_type: str = ANOMALY_TYPE
    rule_id: str = RULE_ID


@dataclass(frozen=True, slots=True)
class UnjudgedCell:
    """A cell the rule could not assess, and why.

    Reported rather than skipped. See the module docstring: silence here
    would be indistinguishable from a clean result.
    """

    cell: RfCell
    reason: str


@dataclass(frozen=True, slots=True)
class RfNoiseFindings:
    """What the rule concluded, including what it could not conclude."""

    anomalies: tuple[RfNoiseAnomaly, ...] = ()
    unjudged: tuple[UnjudgedCell, ...] = ()


@dataclass(frozen=True, slots=True)
class _Reading:
    """One RF reading reduced to what the rule reads."""

    cell: RfCell
    timestamp: datetime
    value: float
    location: Location


def detect_rf_noise(
    observations: Iterable[CanonicalObservation],
    baselines: BaselineTable,
    policy: ThresholdPolicy,
) -> RfNoiseFindings:
    """Episodes of RF deviation, per sensor-channel cell.

    Deterministic: the same readings and the same baseline always give the
    same findings, and the order the readings arrive in is not an input.
    """
    if baselines.metric is not policy.metric:
        raise RuleError(
            f"the policy measures {policy.metric.value} and the baseline table "
            f"holds {baselines.metric.value}. Comparing a reading against a "
            "baseline for a different metric produces a number and no meaning."
        )

    readings = _readings(observations, policy.metric)

    per_cell: dict[RfCell, list[_Reading]] = {}
    for reading in readings:
        per_cell.setdefault(reading.cell, []).append(reading)

    anomalies: list[RfNoiseAnomaly] = []
    unjudged: list[UnjudgedCell] = []

    # Sorted so the output does not depend on the order readings arrived in.
    for cell in sorted(per_cell, key=lambda c: (c.sensor_id, c.channel_index)):
        baseline = baselines.baselines.get(cell)
        if baseline is None:
            unjudged.append(
                UnjudgedCell(cell=cell, reason=_why_unjudged(baselines, cell))
            )
            continue
        anomalies.extend(
            _episodes(
                sorted(per_cell[cell], key=lambda r: r.timestamp), baseline.mean, policy
            )
        )

    return RfNoiseFindings(anomalies=tuple(anomalies), unjudged=tuple(unjudged))


def _readings(
    observations: Iterable[CanonicalObservation], metric: RfMetric
) -> list[_Reading]:
    readings: list[_Reading] = []
    for observation in observations:
        payload = observation.payload
        if not isinstance(payload, RfPayload):
            raise RuleError(
                f"{observation.observation_type.value} observation belongs to no "
                "sensor-channel cell. Skipping it would judge fewer readings "
                "than the caller supplied, without saying so."
            )
        readings.append(
            _Reading(
                cell=RfCell(payload.sensor_id, payload.channel_index),
                timestamp=observation.timestamp,
                value=_value(payload, metric),
                location=observation.location,
            )
        )
    return readings


def _value(payload: RfPayload, metric: RfMetric) -> float:
    return payload.power_dbm if metric is RfMetric.POWER_DBM else payload.snr_db


def _why_unjudged(baselines: BaselineTable, cell: RfCell) -> str:
    thin = baselines.insufficient.get(cell)
    if thin is not None:
        return f"baseline had {thin.samples} of {thin.required} samples required"
    return "no baseline for this cell"


def _episodes(
    readings: Sequence[_Reading], mean: float, policy: ThresholdPolicy
) -> list[RfNoiseAnomaly]:
    """Contiguous runs of exceeding readings, in time order, as anomalies."""
    episodes: list[RfNoiseAnomaly] = []
    current: list[tuple[_Reading, float]] = []

    for reading in readings:
        deviation = _deviation(reading.value, mean, policy.direction)
        if deviation > policy.threshold:
            current.append((reading, deviation))
            continue
        # A reading inside the threshold ends the episode: two events with
        # quiet between them must not become one spanning the quiet.
        if current:
            episodes.append(_anomaly(current, policy))
            current = []

    if current:
        episodes.append(_anomaly(current, policy))
    return episodes


def _deviation(value: float, mean: float, direction: Direction) -> float:
    """How far the wrong way, signed so that larger is always worse."""
    return value - mean if direction is Direction.ABOVE else mean - value


def _anomaly(
    episode: list[tuple[_Reading, float]], policy: ThresholdPolicy
) -> RfNoiseAnomaly:
    readings = [reading for reading, _ in episode]
    peak = max(deviation for _, deviation in episode)
    return RfNoiseAnomaly(
        cell=readings[0].cell,
        metric=policy.metric,
        severity=policy.severity_for(peak),
        started_at=readings[0].timestamp,
        ended_at=readings[-1].timestamp,
        location=readings[0].location,
        peak_deviation=peak,
        triggering=tuple(
            ReadingRef(
                sensor_id=reading.cell.sensor_id,
                channel_index=reading.cell.channel_index,
                timestamp=reading.timestamp,
            )
            for reading in readings
        ),
    )
