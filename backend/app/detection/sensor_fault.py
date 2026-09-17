"""The sensor-fault rule, `SENSOR-FAULT`. Spec: anom-007.

`anom-001` decides whether a reading is abnormal. This decides what the
*pattern* of abnormality implicates -- a receiver that has broken, or a
cause out in the world -- and it is the first rule in the project that
reasons about another rule's output rather than about observations alone.

Two pieces of evidence, kept apart on purpose.

**Geography.** Interference has a location and reaches whatever is near
it, so a receiver away from its normal while its close neighbours sit at
theirs is describing itself and not the air. Receivers going together is
the environment, and this rule must stay silent on it. Neighbour selection
is great-circle distance from the layout at a configured radius, never a
list: a hard-coded neighbour table is a second copy of the layout, and the
two would diverge the first time a receiver moved.

**Frequency.** A real emission spills into the channels either side of the
one it sits on, so a lone raised channel between two normal ones is a
pattern the physics does not easily produce -- evidence about the
instrument by an entirely independent route. The whole plan rising
together is the weaker claim, because a wideband emitter parked beside the
receiver looks the same from here, and that is why confidence is Low there
and High for the isolated channel. The two tests are carried as two
records rather than one blended score, because an analyst reading the
bundle needs to see which one is carrying the argument.

**Nominality is measured from readings, and that is a correction.** Built
on `anom-001`'s episodes instead, this rule claimed 21 of 60 interference
runs as broken receivers. The injected elevation varies per cell per tick
-- 8 dB scaled by 1 + 0.25 of a normal draw -- against a 6 dB threshold,
so about one tick in six falls short and ends the episode: a staged cell
emits a median of six episodes where the incident is one. Two receivers
loud through the same window then have fragments that never overlap, and
each reads as isolated from the other. Measured over the 120 staged runs,
the neighbours in those windows sat 2.51 dB above their own baselines at
the 5th percentile and 4.46 at the median, and *not one* of them crossed
the anomaly threshold there. "Was this receiver anomalous" is a different
question from "was this receiver nominal", and only the second one is this
rule's. Asking it of the readings removed all 21 misattributions and cost
none of the 60 catches.

The bar sits in a measured gap: untouched neighbours reach 1.58 dB at the
95th percentile, touched ones 2.51 dB at the 5th. It is kept in decibels
rather than in multiples of the baseline's spread because that is
`anom-003`, and keeping the two apart is what makes them independent
evidence about one reading rather than one detector counted twice.

**The verdict is three-valued, and the third value is the point.** A
neighbour with no baseline, or with no readings in the window, cannot be
called nominal: missing data is not an observation of normality, and
reading it as one turns silence into a fault diagnosis. So a raised
neighbour settles it as environmental, neighbours all measured and all
nominal settle it as a fault, and anything unmeasurable is recorded as
undecided with the reason. Positive evidence outranks missing data; missing
data outranks an inference drawn from silence. The same argument makes a
receiver with *no* neighbour inside the radius undecided rather than a
fault -- no neighbours means no raised neighbours, which read as a pass
would turn every RF anomaly in the layout into a broken receiver.

**The unit of judgement is one receiver over one window**, not one cell
episode and not one fragment: a fault is a property of a box. `anom-001`'s
episodes are the *seed* -- they say a receiver is worth asking about -- and
the readings are the boundary, because the event began where the receiver
left its baseline rather than where a threshold happened to be crossed.
Windows still split where the receiver returns to nominal, for the reason
`anom-001` gives at reading level: one window must not span the quiet
between two events.

**No track evidence reaches here at all**, and `anom-013` puts this rule
first because of it. The radio side separates an 8 dB elevation from a
1.5 dB spread, beyond five sigma; the track side's rate excess reaches a
Youden's J of 0.40 over 40 matched pairs. Asking the weaker signal to
arbitrate what the stronger one settles was the error that produced a
70 per cent misattribution rate. Now that this rule takes observations at
all, a track observation among them is refused rather than skipped, which
is what keeps that guarantee structural.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.dal.models import CanonicalObservation, Location, RfPayload
from app.detection.baseline import BaselineTable, RfCell, RfMetric
from app.detection.rf_noise import RfNoiseFindings
from app.scenario.layout import RfLayout

#: Travels with every anomaly this rule raises (FR-402), and distinguishes
#: it from `RF-NOISE`, whose findings this one reasons about.
RULE_ID = "SENSOR-FAULT"

#: The anomaly's own type. `possible_`, because the rule reports evidence
#: about an instrument to an analyst and does not condemn it (FR-307).
ANOMALY_TYPE = "possible_sensor_fault"

#: How far a receiver may sit from its own baseline and still be called
#: nominal, in the metric's units. Measured rather than chosen: over the
#: 120 staged runs, a neighbour the incident touched sits 2.51 dB above
#: its baseline at the 5th percentile and one it did not touch reaches
#: 1.58 dB at the 95th, so 2 dB lies in the gap between the populations.
#: The choice is a plateau and not a cliff -- 1.0 and 1.5 dB give the same
#: result on that corpus, 3.0 and 4.0 begin to lose it.
DEFAULT_NOMINAL_WITHIN_DB = 2.0

#: Which way past the baseline the metric moves when noise rises. Fixed
#: rather than configured: noise rising raises power and drives SNR down,
#: so this is a property of the metric, and a direction a caller can set
#: wrongly is a silent wrong answer rather than a loud one.
_RISES: Mapping[RfMetric, bool] = {
    RfMetric.POWER_DBM: True,
    RfMetric.SNR_DB: False,
}


class FaultError(ValueError):
    """The rule was asked for something it could only answer misleadingly."""


class Verdict(str, Enum):
    """What the rule concluded about one receiver over one window."""

    FAULT = "fault"
    #: A neighbour was raised too, so the cause is out there.
    ENVIRONMENTAL = "environmental"
    #: Nothing to compare against, or a neighbour nobody could measure.
    UNDECIDED = "undecided"


class Confidence(str, Enum):
    """Low, Medium or High -- never a percentage and never a decimal.

    It qualifies the *attribution*, not the deviation: `anom-001` already
    carries how far past normal the reading went, as a severity. These are
    different quantities, and folding them together would let a large
    deviation in an unconvincing pattern read as strong evidence about the
    instrument.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class FaultPolicy:
    """How far away a receiver still counts as a neighbour, and how far
    from its baseline it may sit and still be nominal.

    The radius's `None` defers to the layout's own discrimination radius,
    which `scn-005` validates as leaving every sensor at least one
    neighbour inside it and at least one beyond. That is a principled
    default rather than a chosen number -- unlike `anom-012`'s radius,
    which is a trade between a missed incident and a misattributed one and
    therefore has no default at all.
    """

    neighbour_radius_km: float | None = None
    nominal_within_db: float = DEFAULT_NOMINAL_WITHIN_DB

    def __post_init__(self) -> None:
        if self.neighbour_radius_km is not None and self.neighbour_radius_km <= 0:
            raise FaultError(
                f"neighbour radius must be positive, got "
                f"{self.neighbour_radius_km}. A radius of zero has no "
                "neighbours by construction, so every anomaly would be "
                "undecided and the rule would never fail loudly."
            )
        if self.nominal_within_db <= 0:
            raise FaultError(
                f"nominality bar must be positive, got {self.nominal_within_db}. "
                "At zero every neighbour is abnormal on floating-point noise, "
                "so every fault becomes environmental and the rule silently "
                "never fires."
            )

    def radius_for(self, layout: RfLayout) -> float:
        if self.neighbour_radius_km is None:
            return layout.discrimination_radius_km
        return self.neighbour_radius_km


@dataclass(frozen=True, slots=True)
class SpatialEvidence:
    """The neighbour test: who was asked, and what they read."""

    radius_km: float
    nominal_within_db: float
    #: The receivers inside the radius, nearest first. Empty means the test
    #: compared nothing, which is a refusal and never a pass.
    neighbours: tuple[str, ...]
    #: Those measurably away from their own baseline in this window.
    abnormal: tuple[str, ...]
    #: Those with no baseline or no readings, which is not the same as
    #: nominal and must never be read as it.
    unjudged: tuple[str, ...]
    #: Per neighbour, how far it sat from its baseline, in the metric's
    #: units. "RF-02 sat 5.0 dB above its own normal" is a sentence an
    #: analyst can check; "RF-02 was abnormal" is not.
    elevations: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class SpectralEvidence:
    """The frequency-adjacency test, on the receiver itself.

    Kept as its own record rather than folded into the spatial verdict:
    the two are evidence of different kinds, and which one carries the
    argument is exactly what an analyst needs to see.
    """

    #: The channels of this receiver away from their baseline in this
    #: window. Measured, like the neighbour test and for the same reason.
    channels: tuple[int, ...]
    #: The adjacent indices around them, which is what was examined.
    adjacent_checked: tuple[int, ...]
    #: Those raised too -- the deviation spread.
    adjacent_abnormal: tuple[int, ...]
    #: Those that could not be measured, over which isolation cannot be
    #: claimed: the channel might have been raised and nobody would know.
    adjacent_unjudged: tuple[int, ...]
    #: How many channels the receiver reports on, for the broadband test.
    plan_size: int

    @property
    def isolated(self) -> bool:
        """The deviation did not reach an adjacent channel."""
        return not self.adjacent_abnormal

    @property
    def broadband(self) -> bool:
        """Every channel on the receiver went together."""
        return len(self.channels) == self.plan_size

    @property
    def confidence(self) -> Confidence:
        if self.broadband:
            # A wideband emitter beside the receiver produces this too.
            return Confidence.LOW
        if self.adjacent_abnormal or self.adjacent_unjudged:
            # Either the deviation spread, or a channel that would show
            # whether it spread could not be measured.
            return Confidence.MEDIUM
        return Confidence.HIGH


@dataclass(frozen=True, slots=True)
class SensorFault:
    """One receiver implicated over one window."""

    sensor_id: str
    started_at: datetime
    ended_at: datetime
    #: Where the receiver stands. A point: one instrument's fault is at
    #: that instrument and nowhere else, and an area would claim ground
    #: nothing was observed across.
    location: Location
    confidence: Confidence
    spatial: SpatialEvidence
    spectral: SpectralEvidence
    anomaly_type: str = ANOMALY_TYPE
    rule_id: str = RULE_ID


@dataclass(frozen=True, slots=True)
class Dismissal:
    """A receiver this rule looked at and declined to claim, and why.

    This rule's half of `anom-013`'s audit trail: the ladder has to be able
    to say why a zone was not claimed here before offering it to the next
    rule, and a dismissal a reader cannot check is an assertion.
    """

    sensor_id: str
    started_at: datetime
    ended_at: datetime
    verdict: Verdict
    reason: str
    spatial: SpatialEvidence
    spectral: SpectralEvidence


@dataclass(frozen=True, slots=True)
class SensorFaultFindings:
    """What the rule concluded, including what it declined to conclude."""

    faults: tuple[SensorFault, ...] = ()
    dismissed: tuple[Dismissal, ...] = ()


@dataclass(frozen=True, slots=True)
class _Window:
    """One receiver, over one period it was away from its baseline."""

    sensor_id: str
    started_at: datetime
    ended_at: datetime
    location: Location


class _Readings:
    """The run's RF grid, indexed the way the two tests read it.

    Deviations are signed so that larger is always further from nominal,
    in whichever direction the metric moves when noise rises.
    """

    def __init__(
        self, observations: Iterable[CanonicalObservation], baselines: BaselineTable
    ) -> None:
        rises = _RISES[baselines.metric]
        self._cells: dict[RfCell, list[tuple[datetime, float]]] = {}
        self._ticks: dict[str, dict[datetime, float]] = {}
        for observation in observations:
            payload = observation.payload
            if not isinstance(payload, RfPayload):
                raise FaultError(
                    f"{observation.observation_type.value} observation belongs to "
                    "no sensor-channel cell. This rule decides on the radio "
                    "pattern alone (anom-013), so evidence of another kind is "
                    "refused rather than quietly ignored."
                )
            cell = RfCell(payload.sensor_id, payload.channel_index)
            baseline = baselines.baselines.get(cell)
            if baseline is None:
                continue
            if baseline.metric is not baselines.metric:
                raise FaultError(
                    f"baseline for {cell.sensor_id} channel {cell.channel_index} "
                    f"measures {baseline.metric.value} inside a table of "
                    f"{baselines.metric.value}. Comparing a reading against a "
                    "baseline for a different metric produces a number and no "
                    "meaning."
                )
            value = (
                payload.power_dbm
                if baselines.metric is RfMetric.POWER_DBM
                else payload.snr_db
            )
            deviation = value - baseline.mean if rises else baseline.mean - value
            self._cells.setdefault(cell, []).append((observation.timestamp, deviation))
            ticks = self._ticks.setdefault(payload.sensor_id, {})
            ticks[observation.timestamp] = max(
                ticks.get(observation.timestamp, deviation), deviation
            )

    def mean_deviation(
        self, cell: RfCell, window: tuple[datetime, datetime]
    ) -> float | None:
        """How far this cell sat from its baseline across the window.

        `None` when nothing can be said: no baseline, or no reading inside
        the window. Both are the absence of evidence and neither is
        evidence of nominality.
        """
        series = self._cells.get(cell)
        if series is None:
            return None
        inside = [d for at, d in series if window[0] <= at <= window[1]]
        if not inside:
            return None
        return sum(inside) / len(inside)

    def timeline(self, sensor_id: str) -> list[tuple[datetime, float]]:
        """Per instant, the worst deviation across the receiver's channels."""
        return sorted(self._ticks.get(sensor_id, {}).items())


def detect_sensor_faults(
    findings: RfNoiseFindings,
    observations: Iterable[CanonicalObservation],
    baselines: BaselineTable,
    layout: RfLayout,
    policy: FaultPolicy,
) -> SensorFaultFindings:
    """Receivers implicated by their own pattern of deviation.

    Deterministic: the same inputs in a different order are the same
    findings, which the sorting below is what guarantees (NFR-601).
    """
    radius = policy.radius_for(layout)
    known = {site.sensor_id for site in layout.sensors}
    for anomaly in findings.anomalies:
        if anomaly.cell.sensor_id not in known:
            raise FaultError(
                f"anomaly from {anomaly.cell.sensor_id}, which is not in this "
                "layout. The findings and the layout describe different "
                "deployments, and a neighbour test across the two is arithmetic "
                "without meaning."
            )

    readings = _Readings(observations, baselines)
    windows = _windows(findings, readings, layout, policy.nominal_within_db)

    faults: list[SensorFault] = []
    dismissed: list[Dismissal] = []

    for window in windows:
        spectral = _spectral(window, readings, layout, policy.nominal_within_db)
        spatial = _spatial(window, readings, layout, radius, spectral, policy)

        if not spectral.channels:
            dismissed.append(
                _dismissal(
                    window,
                    spatial,
                    spectral,
                    Verdict.UNDECIDED,
                    f"{window.sensor_id}'s readings sit inside "
                    f"{policy.nominal_within_db:g} dB of its own baseline across "
                    "this window, so there is no pattern here to attribute. An "
                    "episode `anom-001` raised on a threshold crossing its window "
                    "does not sustain is not evidence about an instrument.",
                )
            )
            continue

        if not spatial.neighbours:
            dismissed.append(
                _dismissal(
                    window,
                    spatial,
                    spectral,
                    Verdict.UNDECIDED,
                    f"no receiver within {radius:g} km of {window.sensor_id}, so "
                    "the neighbour test compares nothing and cannot separate an "
                    "instrument from its surroundings",
                )
            )
            continue

        if spatial.abnormal:
            dismissed.append(
                _dismissal(
                    window,
                    spatial,
                    spectral,
                    Verdict.ENVIRONMENTAL,
                    f"{', '.join(spatial.abnormal)} sat more than "
                    f"{policy.nominal_within_db:g} dB from its own baseline in the "
                    "same window, which is a cause reaching more than one receiver",
                )
            )
            continue

        if spatial.unjudged:
            dismissed.append(
                _dismissal(
                    window,
                    spatial,
                    spectral,
                    Verdict.UNDECIDED,
                    f"{', '.join(spatial.unjudged)} could not be measured here, "
                    "and a receiver nobody could read is not a receiver reading "
                    "nominally",
                )
            )
            continue

        faults.append(
            SensorFault(
                sensor_id=window.sensor_id,
                started_at=window.started_at,
                ended_at=window.ended_at,
                location=window.location,
                confidence=spectral.confidence,
                spatial=spatial,
                spectral=spectral,
            )
        )

    return SensorFaultFindings(faults=tuple(faults), dismissed=tuple(dismissed))


def _windows(
    findings: RfNoiseFindings,
    readings: _Readings,
    layout: RfLayout,
    bar: float,
) -> tuple[_Window, ...]:
    """Each receiver's periods away from nominal, seeded by the episodes.

    `anom-001`'s episodes say which receivers are worth asking about; the
    readings say where each event began and ended. Taking the boundary
    from the episodes instead makes one incident arrive as a string of
    fragments, because the injected elevation dips below the anomaly
    threshold about one tick in six.
    """
    seeds: dict[str, list[tuple[datetime, datetime]]] = {}
    for anomaly in findings.anomalies:
        seeds.setdefault(anomaly.cell.sensor_id, []).append(
            (anomaly.started_at, anomaly.ended_at)
        )

    windows: list[_Window] = []
    for sensor_id in sorted(seeds):
        site = layout.site(sensor_id)
        spans = _extend(seeds[sensor_id], readings.timeline(sensor_id), bar)
        windows.extend(
            _Window(
                sensor_id=sensor_id,
                started_at=start,
                ended_at=end,
                # From the layout rather than from the episode: every
                # episode on a receiver carries the same point, and taking
                # it from the layout means the two cannot disagree.
                location=Location(lat=site.lat, lon=site.lon),
            )
            for start, end in spans
        )
    return tuple(windows)


def _extend(
    seeds: list[tuple[datetime, datetime]],
    timeline: list[tuple[datetime, float]],
    bar: float,
) -> list[tuple[datetime, datetime]]:
    """Grow each seed to the run of instants the receiver was not nominal.

    Seeds falling in the same run collapse into one, which is what makes a
    fragmented incident one fault. A seed with no timeline under it -- no
    readings at all for that receiver -- keeps its own bounds rather than
    disappearing, since the episode is evidence the caller supplied.
    """
    raised = [at for at, deviation in timeline if deviation > bar]
    spans: list[tuple[datetime, datetime]] = []

    # Not sorted: each seed is extended on its own and the merge below
    # orders the result. Sorting here as well would be a second
    # guarantee of the same thing, which no test could hold.
    for start, end in seeds:
        inside = [at for at in raised if start <= at <= end]
        if not inside:
            spans.append((start, end))
            continue
        first = raised.index(inside[0])
        last = raised.index(inside[-1])
        # Walk out while consecutive instants are still above the bar.
        while first > 0 and _adjacent(timeline, raised[first - 1], raised[first]):
            first -= 1
        while last + 1 < len(raised) and _adjacent(
            timeline, raised[last], raised[last + 1]
        ):
            last += 1
        spans.append((min(start, raised[first]), max(end, raised[last])))

    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            continue
        merged.append((start, end))
    return merged


def _adjacent(
    timeline: list[tuple[datetime, float]], left: datetime, right: datetime
) -> bool:
    """Whether two raised instants have no reading between them.

    A nominal reading in the gap ends the event, on `anom-001`'s argument:
    two events with quiet between them must not become one spanning it.
    """
    return not any(left < at < right for at, _ in timeline)


def _spectral(
    window: _Window, readings: _Readings, layout: RfLayout, bar: float
) -> SpectralEvidence:
    plan = tuple(channel.index for channel in layout.channels)
    span = (window.started_at, window.ended_at)

    raised: list[int] = []
    unmeasured: set[int] = set()
    for channel in plan:
        deviation = readings.mean_deviation(RfCell(window.sensor_id, channel), span)
        if deviation is None:
            unmeasured.add(channel)
        elif deviation > bar:
            raised.append(channel)

    checked: set[int] = set()
    for channel in raised:
        checked.update(layout.adjacent_channels(channel))

    return SpectralEvidence(
        channels=tuple(raised),
        adjacent_checked=tuple(sorted(checked)),
        adjacent_abnormal=tuple(sorted(checked & set(raised))),
        adjacent_unjudged=tuple(sorted(checked & unmeasured)),
        plan_size=len(plan),
    )


def _spatial(
    window: _Window,
    readings: _Readings,
    layout: RfLayout,
    radius: float,
    spectral: SpectralEvidence,
    policy: FaultPolicy,
) -> SpatialEvidence:
    neighbours = layout.neighbours(window.sensor_id, radius)
    span = (window.started_at, window.ended_at)
    # The channels the subject was raised on are the ones a shared cause
    # would have reached. Never empty: a window in which the subject shows
    # no raised channel is refused before this is reached.
    channels = spectral.channels

    abnormal: list[str] = []
    unjudged: list[str] = []
    elevations: list[tuple[str, float]] = []

    for identifier in neighbours:
        measured = [
            readings.mean_deviation(RfCell(identifier, channel), span)
            for channel in channels
        ]
        seen = [value for value in measured if value is not None]
        if seen:
            worst = max(seen)
            elevations.append((identifier, worst))
            if worst > policy.nominal_within_db:
                abnormal.append(identifier)
                continue
        if len(seen) < len(measured):
            # Positive evidence first: a neighbour already shown to be
            # raised settles the question whatever else is missing.
            unjudged.append(identifier)

    return SpatialEvidence(
        radius_km=radius,
        nominal_within_db=policy.nominal_within_db,
        neighbours=neighbours,
        abnormal=tuple(abnormal),
        unjudged=tuple(unjudged),
        elevations=tuple(elevations),
    )


def _dismissal(
    window: _Window,
    spatial: SpatialEvidence,
    spectral: SpectralEvidence,
    verdict: Verdict,
    reason: str,
) -> Dismissal:
    return Dismissal(
        sensor_id=window.sensor_id,
        started_at=window.started_at,
        ended_at=window.ended_at,
        verdict=verdict,
        reason=reason,
        spatial=spatial,
        spectral=spectral,
    )
