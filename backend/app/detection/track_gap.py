"""The track continuity rule, `TRACK-GAP`. Spec: anom-010.

The aircraft side of detection. `anom-004` clusters what this produces and
`anom-006` discriminates on it, so this is the rule the fusion pair rests
on -- and it was the one requirement (FR-304) that had no spec item until
Phase 8 was picked up.

**Its output is an intermediate finding, not a reportable anomaly**, and
that distinction is the whole reason this module reads the way it does. A
quiet run genuinely contains around 138 aircraft, of roughly 530 seen,
whose reported position staleness passes 100 s. Those are properties of
real replayed data at the edges of receiver coverage, not defects. A rule
emitting none of them would not be a quiet detector but a blind one, which
is why `anom-008` was amended alongside this item rather than this item
being tuned until the control went green.

What this rule can do is notice that continuity broke. What it cannot do
is say *why*, and no threshold will fix that: measured across the twenty
runs of each type, staged GNSS degradation exceeds the quiet background by
about 3.4 aircraft per run against 137.7, and above 600 s the quiet runs
are higher. The injection stages 100-300 s disruptions because that is
what a plausible real coverage failure looks like -- and it is also what a
real one is. Attribution is spatial and cross-modal by design.

**Two mechanisms, because the two scenario types stage differently.**
`gnss-degradation` rewrites the reported position staleness and the rows
keep arriving; `aircraft-coverage-gap` suppresses the rows, so there is no
field left to read and the gap is the absence itself. A rule with one
mechanism is blind to one type.

**Frozen position requires fresh contact**, which is a measured decision
rather than a tidy one. Requiring it alongside stale position -- the
two-clock discriminator `dal-001` documents -- takes the quiet-run
background from 137.7 aircraft per run to 24.6 while leaving the staged
margin unchanged, improving signal against background from about one in
forty to one in seven, at no cost.

**Two filters, both corrections the corpus work already needed.** An
aircraft on the ground stopped reporting because it was switched off. A
gap whose ends are not comfortably inside the bounding box is an aircraft
that flew out and back. Measured on the quiet runs: 164 intervals pass
100 s, 32 survive the airborne filter, 23 survive both -- so without them
four fifths of what this reported would be artefacts.

The `adp-008` exclusion list is deliberately **not** applied here. It is
the generator's business to keep known-bad tracks out of a run, and adding
a second copy of that rule is the trap this project has already recorded
once, when a remedy existed in two places and the third caller did not
know about it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from app.dal.models import CanonicalObservation, Location, TrackPayload

#: Travels with every finding, into the cluster and from there into the
#: evidence bundle (FR-402).
RULE_ID = "TRACK-GAP"

#: The finding's type. Not an anomaly type: nothing here reaches an analyst.
FINDING_TYPE = "track_continuity_gap"

#: `adp-008`'s margin, so this rule and the corpus tooling agree about what
#: "comfortably inside the box" means.
DEFAULT_INTERIOR_MARGIN_DEG = 0.25


class RuleError(ValueError):
    """The rule was configured in a way that could only mislead."""


class GapShape(str, Enum):
    """Which of the two signatures the discontinuity has.

    Carried on the finding because telling them apart is precisely what
    `anom-005` and `anom-006` do: a frozen position beside co-located RF
    noise is interference, an aircraft not heard from with a quiet radio
    is a data-source failure.
    """

    #: Still transmitting, position stopped advancing.
    FROZEN_POSITION = "frozen_position"
    #: Not heard from at all; the reports stopped arriving.
    NOT_HEARD = "not_heard"


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """The corpus box, in degrees. Coordinates only, per `dal-001`."""

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def interior(self, location: Location, margin_deg: float) -> bool:
        """Whether a point sits inside by at least the margin on all sides."""
        return (
            self.lat_min + margin_deg <= location.lat <= self.lat_max - margin_deg
            and self.lon_min + margin_deg <= location.lon <= self.lon_max - margin_deg
        )


@dataclass(frozen=True, slots=True)
class GapPolicy:
    """What counts as broken continuity. Configuration, not literals.

    `box` is optional because the interior test is a correction for having
    drawn a box around a corpus; a purely synthetic stream has no box and
    needs no such correction.
    """

    threshold: timedelta
    contact_fresh_within: timedelta
    box: BoundingBox | None = None
    interior_margin_deg: float = DEFAULT_INTERIOR_MARGIN_DEG

    def __post_init__(self) -> None:
        if self.threshold <= timedelta(0):
            raise RuleError(
                f"threshold={self.threshold!r} must be positive: a zero "
                "threshold makes every interval a discontinuity."
            )
        if self.contact_fresh_within >= self.threshold:
            raise RuleError(
                f"contact_fresh_within={self.contact_fresh_within!r} must be "
                f"shorter than threshold={self.threshold!r}. If contact may be "
                "as stale as the threshold the two shapes stop being "
                "exclusive, and one event is reported as both."
            )


@dataclass(frozen=True, slots=True)
class TrackGapFinding:
    """One discontinuity in one aircraft's reporting.

    **No severity field, deliberately.** Severity is what an analyst is
    shown, and nothing here is shown to one.
    """

    aircraft_id: str
    shape: GapShape
    started_at: datetime
    ended_at: datetime
    #: Where the aircraft was last known to be.
    location: Location
    finding_type: str = FINDING_TYPE
    rule_id: str = RULE_ID

    @property
    def duration(self) -> timedelta:
        """Derived rather than stored, so it cannot disagree with the ends."""
        return self.ended_at - self.started_at


@dataclass(frozen=True, slots=True)
class _Report:
    """One track report reduced to what the rule reads."""

    aircraft_id: str
    timestamp: datetime
    location: Location
    on_ground: bool
    position_staleness: timedelta
    contact_staleness: timedelta


def detect_track_gaps(
    observations: Iterable[CanonicalObservation], policy: GapPolicy
) -> tuple[TrackGapFinding, ...]:
    """Discontinuities per aircraft, by both mechanisms.

    Deterministic: the same reports always give the same findings, and the
    order they arrive in is not an input.
    """
    per_aircraft: dict[str, list[_Report]] = {}
    for report in _reports(observations):
        per_aircraft.setdefault(report.aircraft_id, []).append(report)

    findings: list[TrackGapFinding] = []
    # Sorted so the output does not depend on arrival order.
    for aircraft_id in sorted(per_aircraft):
        reports = sorted(per_aircraft[aircraft_id], key=lambda r: r.timestamp)
        found = [*_not_heard(reports, policy), *_frozen(reports, policy)]
        findings.extend(sorted(found, key=lambda f: (f.started_at, f.shape.value)))

    return tuple(findings)


def _reports(observations: Iterable[CanonicalObservation]) -> list[_Report]:
    reports: list[_Report] = []
    for observation in observations:
        payload = observation.payload
        if not isinstance(payload, TrackPayload):
            raise RuleError(
                f"{observation.observation_type.value} observation belongs to no "
                "aircraft. Skipping it would judge less than the caller supplied, "
                "without saying so."
            )
        reports.append(
            _Report(
                aircraft_id=payload.aircraft_id,
                timestamp=observation.timestamp,
                location=observation.location,
                on_ground=payload.on_ground,
                position_staleness=timedelta(seconds=payload.position_staleness_s),
                contact_staleness=timedelta(seconds=payload.contact_staleness_s),
            )
        )
    return reports


def _not_heard(reports: Sequence[_Report], policy: GapPolicy) -> list[TrackGapFinding]:
    """Intervals between consecutive reports that are too long.

    Only gaps bracketed by two real reports count. Nothing is extrapolated
    past the last report: every aircraft still in flight is stale when the
    run ends, so a trailing gap would fire on all of them at once.
    """
    findings: list[TrackGapFinding] = []
    for before, after in zip(reports, reports[1:], strict=False):
        if after.timestamp - before.timestamp <= policy.threshold:
            continue
        if before.on_ground or after.on_ground:
            continue
        if not _both_interior(before, after, policy):
            continue
        findings.append(
            TrackGapFinding(
                aircraft_id=before.aircraft_id,
                shape=GapShape.NOT_HEARD,
                started_at=before.timestamp,
                ended_at=after.timestamp,
                location=before.location,
            )
        )
    return findings


def _both_interior(before: _Report, after: _Report, policy: GapPolicy) -> bool:
    if policy.box is None:
        return True
    return policy.box.interior(
        before.location, policy.interior_margin_deg
    ) and policy.box.interior(after.location, policy.interior_margin_deg)


def _frozen(reports: Sequence[_Report], policy: GapPolicy) -> list[TrackGapFinding]:
    """Runs of reports whose position is stale while contact stays fresh."""
    findings: list[TrackGapFinding] = []
    episode: list[_Report] = []

    for report in reports:
        if _is_frozen(report, policy):
            episode.append(report)
            continue
        if episode:
            findings.append(_frozen_finding(episode))
            episode = []

    if episode:
        findings.append(_frozen_finding(episode))
    return findings


def _is_frozen(report: _Report, policy: GapPolicy) -> bool:
    return (
        not report.on_ground
        and report.position_staleness > policy.threshold
        and report.contact_staleness < policy.contact_fresh_within
    )


def _frozen_finding(episode: Sequence[_Report]) -> TrackGapFinding:
    first = episode[0]
    return TrackGapFinding(
        aircraft_id=first.aircraft_id,
        shape=GapShape.FROZEN_POSITION,
        # When the position was last fresh, not when the rule noticed it.
        # The reported staleness says how far back the last good fix was.
        started_at=first.timestamp - first.position_staleness,
        ended_at=episode[-1].timestamp,
        location=first.location,
    )
