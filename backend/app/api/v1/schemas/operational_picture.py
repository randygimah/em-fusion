"""The operational picture payload. Spec: api-002.

The server half of a contract whose other half is
`frontend/src/types/operationalPicture.ts`. Nothing checks the two against each
other at compile time -- they are two declarations of one shape in two
languages -- so a test parses the TypeScript and compares field sets in both
directions. That test is the item's actual deliverable; these models are what
it holds in place.

**Field names are camelCase, and the class names match the interfaces
exactly.** `RFSensor` is not the name Python style would choose. A translation
table between the two sides is a place for them to drift while every test still
passes, so there is deliberately none.

**Absence is a value here, not a gap.** Four of the six sections have no
producer: no detector, no RF source, no generator. Those sections are empty and
the detection summary is null, rather than carrying a plausible reading. `Low`
would be a claim about the data; null is a statement about the system, which is
the only one that can currently be made truthfully. It is the same reasoning
that made `db-007`'s completion flag nullable, and `op-001` already requires the
screen to render with scenario data absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.dal.models import CanonicalObservation, ScenarioRunSummary, TrackPayload

#: Low, Medium, High -- never a percentage and never a decimal (`FR-715`,
#: `AC-11`). Declared once so the fields that carry a level cannot drift into
#: three different vocabularies, exactly as the TypeScript side declares it once.
Level = Literal["Low", "Medium", "High"]

#: One international foot is 0.3048 metres, exactly, by definition. The store
#: holds metres because the source reports them; the contract asks for feet
#: because that is what altitude is read in.
METRES_PER_FOOT = 0.3048

#: Reported when nothing has been served to say otherwise. A guess would be
#: indistinguishable from a fact on screen.
UNKNOWN = "unknown"


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    dataMode: str  # noqa: N815 -- mirrors the TypeScript contract
    health: str


class Hypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    confidence: Level
    severity: Level
    status: Literal["new", "under_review", "reviewed"]
    evidence: str


class DetectionSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    anomalyLevel: Level | None  # noqa: N815 -- mirrors the TypeScript contract
    signalIntegrity: Level | None  # noqa: N815 -- mirrors the contract


class RFSensor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    stationName: str  # noqa: N815 -- mirrors the TypeScript contract
    signalId: str  # noqa: N815 -- mirrors the TypeScript contract
    health: str
    lat: float
    lon: float


class AircraftTrack(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    #: Nullable because 22.7% of positioned rows in the corpus carry no
    #: altitude. An aircraft of unknown height is still an aircraft.
    altitudeFt: int | None  # noqa: N815 -- mirrors the TypeScript contract
    lat: float
    lon: float


class TimelineEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    time: str
    event: str
    source: str


class OperationalPicture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Null before the first run exists, so the screen can be developed and
    #: served against an empty database rather than a 500 (`op-001`).
    scenario: Scenario | None
    hypotheses: list[Hypothesis]
    detectionSummary: DetectionSummary  # noqa: N815 -- mirrors the contract
    rfSensors: list[RFSensor]  # noqa: N815 -- mirrors the contract
    aircraftTracks: list[AircraftTrack]  # noqa: N815 -- mirrors the contract
    timelineEvents: list[TimelineEvent]  # noqa: N815 -- mirrors the contract


def _feet(metres: float | None) -> int | None:
    return None if metres is None else round(metres / METRES_PER_FOOT)


def _track(observation: CanonicalObservation) -> AircraftTrack:
    """One observation as a track.

    The name is whatever the payload holds, which `dal-004` guarantees is a
    pseudonym: the substitution happens at ingest, so nothing here has to
    remember to do it and nothing here could undo it.
    """
    payload = observation.payload
    altitude = payload.altitude_m if isinstance(payload, TrackPayload) else None
    identifier = payload.aircraft_id if isinstance(payload, TrackPayload) else ""
    return AircraftTrack(
        id=f"{observation.source_id}:{identifier}",
        name=identifier,
        altitudeFt=_feet(altitude),
        lat=observation.location.lat,
        lon=observation.location.lon,
    )


def _data_mode(observations: Sequence[CanonicalObservation]) -> str:
    """The mode of what is actually being served, not of what was asked for.

    A run row records no data mode; its observations do. Reported as `mixed`
    when they disagree rather than by taking the first, because a screen
    labelled `replayed` while showing live records is worse than one that
    admits it is showing both.
    """
    modes = {observation.data_mode.value for observation in observations}
    if not modes:
        return UNKNOWN
    if len(modes) > 1:
        return "mixed"
    return modes.pop()


def build_operational_picture(
    *,
    run: ScenarioRunSummary | None,
    observations: Sequence[CanonicalObservation],
) -> OperationalPicture:
    """Assemble the payload from a run and the positions being served.

    A pure function taking what it needs rather than a repository, so every
    judgement in the payload -- the unit conversion, the data mode, what an
    absent detector may claim -- is provable without a database.
    """
    scenario = (
        None
        if run is None
        else Scenario(
            id=str(run.id),
            name=run.scenario_type,
            dataMode=_data_mode(observations),
            # No health monitoring exists. `unknown` says so; `Healthy` would
            # be a reassurance nothing has checked.
            health=UNKNOWN,
        )
    )
    return OperationalPicture(
        scenario=scenario,
        hypotheses=[],
        detectionSummary=DetectionSummary(anomalyLevel=None, signalIntegrity=None),
        rfSensors=[],
        aircraftTracks=[_track(observation) for observation in observations],
        timelineEvents=[],
    )
