"""Receiver states over an hour, for playback. Spec: api-018.

The picture gives each receiver one state for the whole hour: the worst any
stored finding put it in (`api-012`). Playback (`op-008`, `map-004`) moves
through the hour, so a receiver faulted for two minutes would read faulted
from the first second to the last. This serves each receiver's timeline
instead: the intervals in which stored findings put it out of nominal, for
`map-007` to draw at the cursor.

**One ladder, the picture's.** Which finding puts a receiver in which state,
and which state is worse, are `RECEIVER_STATES` and `_receivers_named` from
the picture's own module, imported rather than restated, so the timeline's
worst moment and the whole-hour state cannot disagree.

**Intervals do not overlap.** Where a fault falls inside a deviation the
deviation is served either side of it and the fault between; where two
findings in one state overlap or touch they are one interval. The windows
are closed, as the findings' are, so an instantaneous finding is an interval
of one instant rather than nothing. Every bound served is a stored finding's
bound, so no interval reaches outside the findings it came from.

**A join on stored findings, never re-detected** (`anom-016`), and filtered
by nothing: it is the receivers' timeline, not a view. On an hour no pass
examined, each receiver's intervals are **null** rather than empty, because
empty reads as *nominal all hour* (`api-012`'s distinction).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.operational_picture import (
    RECEIVER_STATES,
    PictureError,
    _of,
    _receivers_named,
)
from app.dal.models import DetectionPass, ScenarioRunSummary
from app.detection.findings import DetectionFinding
from app.scenario.layout import RfLayout

#: The states an interval may carry: the picture's ladder less `nominal`,
#: which is what lies between intervals.
ReceiverOutOfNominal = Literal["fault", "deviating"]

#: The ladder's states, worst first, and each one's rank: worse is higher, and
#: 0 is nominal.
_LADDER = tuple(dict.fromkeys(state for _key, state in RECEIVER_STATES))
_RANK = {state: len(_LADDER) - index for index, state in enumerate(_LADDER)}
_STATE_OF = {rank: state for state, rank in _RANK.items()}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReceiverStateInterval(_Frozen):
    """A closed stretch of simulated time in one state."""

    startedAt: datetime  # noqa: N815 -- mirrors the TypeScript contract
    endedAt: datetime  # noqa: N815
    state: ReceiverOutOfNominal


class ReceiverTimeline(_Frozen):
    id: str
    #: Oldest first and non-overlapping. Null on an unexamined hour; empty
    #: when examined and nominal throughout.
    intervals: list[ReceiverStateInterval] | None


class ReceiverStates(_Frozen):
    runId: int  # noqa: N815
    examined: bool
    #: Every receiver in the layout, in layout order (`scn-005`).
    receivers: list[ReceiverTimeline]


def build_receiver_states(
    *,
    run: ScenarioRunSummary,
    layout: RfLayout,
    findings: Sequence[DetectionFinding] = (),
    detection_pass: DetectionPass | None = None,
) -> ReceiverStates:
    """Each receiver's timeline from what has been read for the run. Pure."""
    scored = detection_pass is not None
    windows: dict[str, list[tuple[datetime, datetime, int]]] = defaultdict(list)
    if scored:
        known = {site.sensor_id for site in layout.sensors}
        for key, state in RECEIVER_STATES:
            for finding in _of(findings, key):
                for sensor in _receivers_named(finding):
                    if sensor not in known:
                        raise PictureError(
                            f"a {finding.rule_id} finding names receiver "
                            f"{sensor!r}, which is not in the layout being "
                            "served. Served, the receiver would show nowhere "
                            "while a rule had named it."
                        )
                    windows[sensor].append(
                        (finding.started_at, finding.ended_at, _RANK[state])
                    )
    return ReceiverStates(
        runId=run.id,
        examined=scored,
        receivers=[
            ReceiverTimeline(
                id=site.sensor_id,
                intervals=_flattened(windows[site.sensor_id]) if scored else None,
            )
            for site in layout.sensors
        ],
    )


def _flattened(
    windows: Sequence[tuple[datetime, datetime, int]],
) -> list[ReceiverStateInterval]:
    """Overlapping closed windows as non-overlapping intervals, worst winning.

    The timeline is cut at every bound into instants and the open stretches
    between them, each given the worst state of the windows covering it.
    Consecutive pieces in one state become one interval. Cutting at instants
    as well as stretches is what keeps a one-instant finding, which a sweep
    over stretches alone would lose.
    """
    bounds = sorted({moment for start, end, _ in windows for moment in (start, end)})
    pieces: list[tuple[datetime, datetime, int]] = []
    for index, moment in enumerate(bounds):
        pieces.append((moment, moment, _worst(windows, moment, moment)))
        if index + 1 < len(bounds):
            following = bounds[index + 1]
            pieces.append((moment, following, _worst(windows, moment, following)))

    intervals: list[ReceiverStateInterval] = []
    run: list[tuple[datetime, datetime, int]] = []
    for piece in [*pieces, (bounds[-1], bounds[-1], 0)] if bounds else []:
        if run and piece[2] != run[-1][2]:
            if run[-1][2]:
                intervals.append(
                    ReceiverStateInterval(
                        startedAt=run[0][0],
                        endedAt=run[-1][1],
                        state=cast(ReceiverOutOfNominal, _STATE_OF[run[-1][2]]),
                    )
                )
            run = []
        run.append(piece)
    return intervals


def _worst(
    windows: Sequence[tuple[datetime, datetime, int]], start: datetime, end: datetime
) -> int:
    """The worst rank among the windows covering all of [start, end]; 0 for none."""
    return max(
        (rank for low, high, rank in windows if low <= start and end <= high),
        default=0,
    )


__all__ = [
    "ReceiverOutOfNominal",
    "ReceiverStateInterval",
    "ReceiverStates",
    "ReceiverTimeline",
    "build_receiver_states",
]
