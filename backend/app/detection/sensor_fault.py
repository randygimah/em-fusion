"""The sensor-fault rule, `SENSOR-FAULT`. Spec: anom-007.

`anom-001` decides whether a reading is abnormal. This decides what the
*pattern* of abnormality implicates -- a receiver that has broken, or a
cause out in the world -- and it is the first rule in the project whose
input is another rule's output rather than observations.

Two pieces of evidence, kept apart on purpose.

**Geography.** Interference has a location and reaches whatever is near it,
so a receiver reading loud while its close neighbours read nominal is
describing itself and not the air. Three adjacent receivers loud together
is the environment, and this rule must stay silent on it. Neighbour
selection is great-circle distance from the layout at a configured radius,
never a list: a hard-coded neighbour table is a second copy of the layout,
and the two would diverge the first time a receiver moved.

**Frequency.** A real emission spills into the channels either side of the
one it sits on, so a lone loud channel between two clean ones is a pattern
the physics does not easily produce -- evidence about the instrument by an
entirely independent route. The whole plan rising together is the weaker
claim, because a wideband emitter parked beside the receiver looks the
same from here, and that is why confidence is Low there and High for the
isolated channel. The two tests are carried as two records rather than one
blended score, because an analyst reading the bundle needs to see which
one is carrying the argument.

**The verdict is three-valued, and the third value is the point.**
`anom-001` reports the cells it could not judge alongside the ones it
could, precisely so that silence is never read as cleanliness. This is the
first consumer with the opportunity to make that mistake: a neighbour that
reported nothing because it had no usable baseline is not a neighbour that
reported nominal. So an abnormal neighbour settles it as environmental,
neighbours all judged and all clean settle it as a fault, and neighbours
clean with anything unjudged is recorded as undecided with the reason.
Positive evidence outranks missing data; missing data outranks an
inference drawn from silence. The same argument makes a sensor with *no*
neighbour inside the radius undecided rather than a fault -- no
neighbours means no abnormal neighbours, which read as a pass would turn
every RF anomaly in the layout into a broken receiver.

**The unit of judgement is one receiver over one merged window**, not one
cell episode: a fault is a property of a box, and per-episode output would
make one broken receiver read as eight sensor faults. Episodes that do not
overlap are not merged, for the reason `anom-001` gives at reading level --
one window must not span the quiet between two events.

**No track evidence reaches here at all**, and `anom-013` puts this rule
first because of it. The radio side separates an 8 dB elevation from a
1.5 dB spread, beyond five sigma; the track side's rate excess reaches a
Youden's J of 0.40 over 40 matched pairs. Asking the weaker signal to
arbitrate what the stronger one settles was the error that produced a
70 per cent misattribution rate, and the enforcement here is structural --
this module's inputs have nowhere to put a track finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.dal.models import Location
from app.detection.rf_noise import RfNoiseAnomaly, RfNoiseFindings
from app.scenario.layout import RfLayout

#: Travels with every anomaly this rule raises (FR-402), and distinguishes
#: it from `RF-NOISE`, whose finding this one reasons about.
RULE_ID = "SENSOR-FAULT"

#: The anomaly's own type. `possible_`, because the rule reports evidence
#: about an instrument to an analyst and does not condemn it (FR-307).
ANOMALY_TYPE = "possible_sensor_fault"


class FaultError(ValueError):
    """The rule was asked for something it could only answer misleadingly."""


class Verdict(str, Enum):
    """What the rule concluded about one receiver over one window."""

    FAULT = "fault"
    #: A neighbour deviated in the same window, so the cause is out there.
    ENVIRONMENTAL = "environmental"
    #: Nothing to compare against, or a neighbour nobody assessed.
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
    """How far away a receiver still counts as a neighbour.

    `None` defers to the layout's own discrimination radius, which
    `scn-005` validates as leaving every sensor at least one neighbour
    inside it and at least one beyond. That is a principled default rather
    than a chosen number -- unlike `anom-012`'s radius, which is a trade
    between a missed incident and a misattributed one and therefore has no
    default at all.
    """

    neighbour_radius_km: float | None = None

    def __post_init__(self) -> None:
        if self.neighbour_radius_km is not None and self.neighbour_radius_km <= 0:
            raise FaultError(
                f"neighbour radius must be positive, got "
                f"{self.neighbour_radius_km}. A radius of zero has no "
                "neighbours by construction, so every anomaly would be "
                "undecided and the rule would never fail loudly."
            )

    def radius_for(self, layout: RfLayout) -> float:
        if self.neighbour_radius_km is None:
            return layout.discrimination_radius_km
        return self.neighbour_radius_km


@dataclass(frozen=True, slots=True)
class SpatialEvidence:
    """The neighbour test: who was asked, and what they said."""

    radius_km: float
    #: The receivers inside the radius, nearest first. Empty means the test
    #: compared nothing, which is a refusal and never a pass.
    neighbours: tuple[str, ...]
    #: Those with an anomaly overlapping this window.
    abnormal: tuple[str, ...]
    #: Those carrying a cell `anom-001` could not judge. Not clean.
    unjudged: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpectralEvidence:
    """The frequency-adjacency test, on the receiver itself.

    Kept as its own record rather than folded into the spatial verdict:
    the two are evidence of different kinds, and which one carries the
    argument is exactly what an analyst needs to see.
    """

    #: The channels of this receiver that deviated in this window.
    channels: tuple[int, ...]
    #: The adjacent indices around them, which is what was examined.
    adjacent_checked: tuple[int, ...]
    #: Those that deviated too -- the deviation spread.
    adjacent_abnormal: tuple[int, ...]
    #: Those nobody assessed, over which isolation cannot be claimed.
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
            # whether it spread was never assessed.
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
    """One receiver's overlapping episodes, merged."""

    sensor_id: str
    started_at: datetime
    ended_at: datetime
    location: Location
    channels: tuple[int, ...]


def detect_sensor_faults(
    findings: RfNoiseFindings,
    layout: RfLayout,
    policy: FaultPolicy,
) -> SensorFaultFindings:
    """Receivers implicated by their own pattern of deviation.

    Deterministic: the same findings in a different order are the same
    findings, which the sorting below is what guarantees (NFR-601).
    """
    radius = policy.radius_for(layout)
    _check_layout(findings, layout)

    unjudged_channels = _unjudged_channels(findings)
    windows = _windows(findings.anomalies, layout)

    faults: list[SensorFault] = []
    dismissed: list[Dismissal] = []

    for window in windows:
        spatial = _spatial(window, windows, layout, radius, unjudged_channels)
        spectral = _spectral(window, layout, unjudged_channels)

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
                    f"{', '.join(spatial.abnormal)} deviated in the same window, "
                    "which is a cause reaching more than one receiver",
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
                    f"{', '.join(spatial.unjudged)} had cells RF-NOISE could not "
                    "judge, and a receiver that reported nothing is not a "
                    "receiver that reported nominal",
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


def _check_layout(findings: RfNoiseFindings, layout: RfLayout) -> None:
    """Refuse findings and a layout that disagree about the receivers.

    Skipping the unknown sensor would judge fewer receivers than were
    reported without saying so, which is the failure `anom-008` exists to
    make impossible elsewhere.
    """
    known = {site.sensor_id for site in layout.sensors}
    for anomaly in findings.anomalies:
        if anomaly.cell.sensor_id not in known:
            raise FaultError(
                f"anomaly from {anomaly.cell.sensor_id}, which is not in this "
                "layout. The findings and the layout describe different "
                "deployments, and a neighbour test across the two is arithmetic "
                "without meaning."
            )


def _unjudged_channels(findings: RfNoiseFindings) -> dict[str, set[int]]:
    """Per receiver, the channels `anom-001` could not assess."""
    channels: dict[str, set[int]] = {}
    for cell in findings.unjudged:
        channels.setdefault(cell.cell.sensor_id, set()).add(cell.cell.channel_index)
    return channels


def _windows(
    anomalies: tuple[RfNoiseAnomaly, ...], layout: RfLayout
) -> tuple[_Window, ...]:
    """Each receiver's episodes, merged where they overlap.

    Overlap is inclusive at both endpoints: an episode's end is its last
    *exceeding* reading rather than the first quiet one, so two episodes
    meeting at a tick shared a reading.
    """
    per_sensor: dict[str, list[RfNoiseAnomaly]] = {}
    for anomaly in anomalies:
        per_sensor.setdefault(anomaly.cell.sensor_id, []).append(anomaly)

    windows: list[_Window] = []
    for sensor_id in sorted(per_sensor):
        group: list[RfNoiseAnomaly] = []
        for anomaly in sorted(
            per_sensor[sensor_id],
            key=lambda a: (a.started_at, a.ended_at, a.cell.channel_index),
        ):
            if group and anomaly.started_at <= max(a.ended_at for a in group):
                group.append(anomaly)
                continue
            if group:
                windows.append(_merge(sensor_id, group, layout))
            group = [anomaly]
        if group:
            windows.append(_merge(sensor_id, group, layout))

    # Already in (sensor, start) order: the loop walks sorted identifiers
    # and appends each sensor's windows in ascending start order. A second
    # sort here would be a redundant guarantee -- and a redundant guarantee
    # is one no test can hold, because either mechanism alone keeps the
    # output right and neither can be made to fail on its own.
    return tuple(windows)


def _merge(sensor_id: str, group: list[RfNoiseAnomaly], layout: RfLayout) -> _Window:
    site = layout.site(sensor_id)
    return _Window(
        sensor_id=sensor_id,
        started_at=min(a.started_at for a in group),
        ended_at=max(a.ended_at for a in group),
        # From the layout rather than from the episode: every episode on a
        # receiver carries the same point, and taking it from the layout
        # means the two cannot disagree.
        location=Location(lat=site.lat, lon=site.lon),
        channels=tuple(sorted({a.cell.channel_index for a in group})),
    )


def _spatial(
    window: _Window,
    windows: tuple[_Window, ...],
    layout: RfLayout,
    radius: float,
    unjudged: dict[str, set[int]],
) -> SpatialEvidence:
    neighbours = layout.neighbours(window.sensor_id, radius)
    abnormal = tuple(
        identifier
        for identifier in neighbours
        if any(
            other.sensor_id == identifier and _overlaps(window, other)
            for other in windows
        )
    )
    return SpatialEvidence(
        radius_km=radius,
        neighbours=neighbours,
        abnormal=abnormal,
        unjudged=tuple(
            identifier for identifier in neighbours if unjudged.get(identifier)
        ),
    )


def _overlaps(left: _Window, right: _Window) -> bool:
    return left.started_at <= right.ended_at and right.started_at <= left.ended_at


def _spectral(
    window: _Window, layout: RfLayout, unjudged: dict[str, set[int]]
) -> SpectralEvidence:
    deviating = set(window.channels)
    checked: set[int] = set()
    for channel in window.channels:
        checked.update(layout.adjacent_channels(channel))
    blind = unjudged.get(window.sensor_id, set())
    return SpectralEvidence(
        channels=window.channels,
        adjacent_checked=tuple(sorted(checked)),
        adjacent_abnormal=tuple(sorted(checked & deviating)),
        adjacent_unjudged=tuple(sorted(checked & blind)),
        plan_size=len(layout.channels),
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
