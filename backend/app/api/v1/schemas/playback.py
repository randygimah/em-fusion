"""Aircraft positions across a span of one run, for playback. Spec: api-008.

The picture answers *where is each aircraft now*; playback (`op-008`,
`map-004`) asks *where was each aircraft at every moment*. A run is fifteen
simulated minutes, about 33,000 positions from about 520 aircraft at a
ten-second cadence -- about 3 MB as JSON -- so the screen asks for one span at a
time and buffers ahead of its cursor, which is what decouples the request rate
from the frame rate (FR-718, FR-810).

**The span is bounded and a longer one is refused, never cut short.** 300 s,
the picture's own final window and about 1 MB under *All*. A truncated answer
would be a partial one the client has to detect; a 422 naming the bound is one
it cannot misread.

**One definition of everything the picture already decides.** The aircraft's
id, name and state, the unit, and what each view admits are the picture's own
functions, imported rather than restated: a playback track and a picture track
join on the id, and the view switch drives both, so a second definition of
*interrupted* here would be a second place for it to drift (`api-007`,
`api-016`).

**Gaps are a join on stored findings, never re-detected.** A two-minute hole in
an aircraft's reports with no stored continuity gap is served as no gap: the
detection pass decided, under its recorded settings, and a request re-running
`anom-010` is what `anom-016` forbids. On an hour no pass examined, the gap list
is **null** rather than empty, because an empty list reads as *looked and found
none* -- `evb-001`'s typed-absence rule on one more field.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.operational_picture import (
    GAP_RULE,
    GAP_TYPE,
    TrackState,
    ViewSelection,
    _admit,
    _feet,
    _interrupted,
    _of,
    _track,
)
from app.dal.models import (
    CanonicalObservation,
    DetectionPass,
    ScenarioRunSummary,
    TrackPayload,
)
from app.detection.findings import DetectionFinding

#: The longest span one request may ask for: the picture's final window, so a
#: span of playback and the picture's "now" are the same size of thing.
MAX_SPAN_SECONDS: Final = 300


class PlaybackError(ValueError):
    """A span the endpoint will not serve, refused before anything is read."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PlaybackPosition(_Frozen):
    """Where one aircraft was at one instant of simulated time."""

    time: datetime
    lat: float
    lon: float
    altitudeFt: int | None  # noqa: N815 -- mirrors the TypeScript contract


class PlaybackGap(_Frozen):
    """One stored continuity gap (`anom-010`) overlapping the span."""

    startedAt: datetime  # noqa: N815
    endedAt: datetime  # noqa: N815


class PlaybackAircraft(_Frozen):
    id: str
    name: str
    state: TrackState
    #: Oldest first, so the client interpolates without sorting.
    positions: list[PlaybackPosition]
    #: Null on an unexamined hour; empty when examined and none overlap.
    gaps: list[PlaybackGap] | None


class PlaybackWindow(_Frozen):
    runId: int  # noqa: N815
    #: The run's first and last position, so the client knows where playback
    #: ends. Null on a run with none.
    recordedFrom: datetime | None  # noqa: N815
    recordedTo: datetime | None  # noqa: N815
    #: The span served, half-open: exactly what was asked for, never shortened.
    servedFrom: datetime  # noqa: N815
    servedTo: datetime  # noqa: N815
    view: ViewSelection
    examined: bool
    #: Aircraft in the span the view did not admit (`api-007`).
    withheld: int
    aircraft: list[PlaybackAircraft]


def check_span(start: datetime, end: datetime) -> None:
    """Refuse a span that is not forwards, not in UTC-aware time, or too long."""
    if start.tzinfo is None or end.tzinfo is None:
        raise PlaybackError("a span needs a timezone; simulated time is UTC")
    if end <= start:
        raise PlaybackError("a span must end after it starts")
    if end - start > timedelta(seconds=MAX_SPAN_SECONDS):
        raise PlaybackError(
            f"a span may be at most {MAX_SPAN_SECONDS} s; ask for the run in pieces"
        )


def _gaps(
    findings: Sequence[DetectionFinding], start: datetime, end: datetime
) -> dict[str, list[PlaybackGap]]:
    """Each aircraft's stored gaps overlapping the half-open span, oldest first."""
    found: dict[str, list[PlaybackGap]] = defaultdict(list)
    for finding in sorted(
        _of(findings, (GAP_RULE, GAP_TYPE)), key=lambda f: f.started_at
    ):
        if finding.started_at < end and finding.ended_at > start:
            found[finding.subject].append(
                PlaybackGap(startedAt=finding.started_at, endedAt=finding.ended_at)
            )
    return found


def _aircraft_id(observation: CanonicalObservation) -> str:
    payload = observation.payload
    return payload.aircraft_id if isinstance(payload, TrackPayload) else ""


def build_playback_window(
    *,
    run: ScenarioRunSummary,
    observations: Sequence[CanonicalObservation],
    recorded: tuple[datetime, datetime] | None,
    start: datetime,
    end: datetime,
    findings: Sequence[DetectionFinding] = (),
    detection_pass: DetectionPass | None = None,
    view: ViewSelection = "all",
) -> PlaybackWindow:
    """Assemble the span from what has been read for it. Pure, like the picture's
    builder, so every judgement is provable without a database."""
    scored = detection_pass is not None
    interrupted = _interrupted(findings) if scored else None
    gaps = _gaps(findings, start, end) if scored else None

    by_aircraft: dict[str, list[CanonicalObservation]] = defaultdict(list)
    for observation in observations:
        by_aircraft[_aircraft_id(observation)].append(observation)

    aircraft: list[PlaybackAircraft] = []
    for identifier, reports in sorted(by_aircraft.items()):
        reports.sort(key=lambda report: report.timestamp)
        # The picture's own track for this aircraft, for its id, name and state.
        track = _track(reports[-1], interrupted=interrupted)
        aircraft.append(
            PlaybackAircraft(
                id=track.id,
                name=track.name,
                state=track.state,
                positions=[
                    PlaybackPosition(
                        time=report.timestamp,
                        lat=report.location.lat,
                        lon=report.location.lon,
                        altitudeFt=_feet(
                            report.payload.altitude_m
                            if isinstance(report.payload, TrackPayload)
                            else None
                        ),
                    )
                    for report in reports
                ],
                gaps=None if gaps is None else gaps.get(identifier, []),
            )
        )

    admitted, withheld = _admit(view, aircraft, lambda entry: entry.state)
    return PlaybackWindow(
        runId=run.id,
        recordedFrom=None if recorded is None else recorded[0],
        recordedTo=None if recorded is None else recorded[1],
        servedFrom=start,
        servedTo=end,
        view=view,
        examined=scored,
        withheld=withheld,
        aircraft=admitted,
    )


__all__ = [
    "MAX_SPAN_SECONDS",
    "PlaybackAircraft",
    "PlaybackError",
    "PlaybackGap",
    "PlaybackPosition",
    "PlaybackWindow",
    "build_playback_window",
    "check_span",
]
