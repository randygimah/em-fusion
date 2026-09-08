"""What a scenario stages, and the answer key that records it. Spec: scn-002.

`scn-001` produces the quiet background. This module decides what is wrong with
a run: which receivers are affected, in which slices of the band, and during
which window. It decides nothing else -- the readings themselves are the
emitter's, and the track side is `tracks.py`'s.

**The incident is planned from the seed, not supplied.** A caller that passed in
the affected sensors would be choosing the answer, and a batch of thirty runs
would need thirty callers to choose thirty different answers. Deriving the site
from the seed means `scn-003`'s batch varies the staging for free, and means
`scn-001`'s different-seeds arm already covers "two runs must not stage the same
incident in the same place".

**Ground truth is produced here and goes nowhere near an observation.** It is
written to the run record at generation time (`api-009`), which is the only
place a detector cannot see it. Nothing in this module is ever consulted while a
reading is being valued except through `Incident`, which carries no scenario
type at all -- so the emitter physically cannot label a cell with what was
staged, whatever anyone later asks it to do.

**Spectral extent is a parameter of both interference types.** Narrowband
confines the injection to the GNSS L1 slice; broadband raises the whole plan.
For `gnss-degradation` that is the difference between a targeted emitter and a
wideband one; for `rf-sensor-fault` it is the difference between the pattern
`anom-007` should read as a faulty receiver and the pattern it should read as
the environment. Neither is a sixth scenario type, and the enum below has
exactly five members for that reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.scenario.layout import L1_CENTRE_MHZ, RfLayout
from app.scenario.seeding import derive_unit

if TYPE_CHECKING:  # pragma: no cover -- import cycle, types only
    from app.scenario.emitter import RunSpec
    from app.scenario.tracks import TrackPerturber


class ScenarioType(str, Enum):
    """The five, and only five (`FR-202`).

    A sixth member is the spec's second failure case. Broadband interference is
    `GNSS_DEGRADATION` with `SpectralExtent.BROADBAND`, which keeps the
    comparison between narrow and wide a comparison within one type rather than
    a confound between two.
    """

    NORMAL_BASELINE = "normal-baseline"
    GNSS_DEGRADATION = "gnss-degradation"
    RF_SENSOR_FAULT = "rf-sensor-fault"
    AIRCRAFT_COVERAGE_GAP = "aircraft-coverage-gap"
    AMBIGUOUS_MIXED_EVIDENCE = "ambiguous-mixed-evidence"


class SpectralExtent(str, Enum):
    """How much of the band an injection touches."""

    NARROWBAND = "narrowband"
    BROADBAND = "broadband"


#: Types that stage something on the RF grid. `aircraft-coverage-gap` is
#: deliberately absent: it is a track-side scenario, and giving it an RF
#: signature would make the data-source rule (`anom-006`) undiscriminating,
#: since that rule fires on dropouts with *no* co-located RF anomaly.
_RF_TYPES = frozenset(
    {
        ScenarioType.GNSS_DEGRADATION,
        ScenarioType.RF_SENSOR_FAULT,
        ScenarioType.AMBIGUOUS_MIXED_EVIDENCE,
    }
)

#: Types affecting exactly one receiver, whose neighbours must stay nominal.
_SINGLE_SENSOR_TYPES = frozenset(
    {ScenarioType.RF_SENSOR_FAULT, ScenarioType.AMBIGUOUS_MIXED_EVIDENCE}
)


class IncidentParameters(BaseModel):
    """What varies between two runs of the same type at the same seed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Simulated seconds from the run's start to the incident's start. The
    #: default leaves quiet ticks on both sides, which is what lets a detector
    #: have a before and an after rather than only a during.
    start_offset_s: int = Field(default=120, ge=0)
    duration_s: int = Field(default=300, gt=0)

    #: How far the affected zone reaches from the receiver at its centre. The
    #: default sits inside the band `scn-005` measured the layout to
    #: discriminate over -- [55.7, 85.7) km -- so a zone reliably contains some
    #: receivers and excludes others.
    radius_km: float = Field(default=60.0, gt=0.0)

    spectral_extent: SpectralExtent = SpectralExtent.NARROWBAND

    #: How far the noise floor rises, in decibels, on an affected cell.
    elevation_db: float = Field(default=8.0, gt=0.0)


@dataclass(frozen=True)
class Incident:
    """What was staged, in the terms the emitter needs to stage it.

    Carries no scenario type. The emitter takes one of these and nothing else,
    so there is no path by which a reading could be labelled with the kind of
    incident that produced it -- `api-009` enforced by what the type cannot
    express rather than by remembering not to.
    """

    sensors: tuple[str, ...]
    channels: tuple[int, ...]
    start: datetime
    end: datetime
    elevation_db: float

    def touches(self, sensor_id: str, channel_index: int, at: datetime) -> bool:
        """Whether this cell is inside the staging, on all three axes."""
        return (
            sensor_id in self.sensors
            and channel_index in self.channels
            and self.start <= at < self.end
        )


def _l1_index(layout: RfLayout) -> int:
    return next(
        channel.index
        for channel in layout.channels
        if channel.centre_frequency_mhz == L1_CENTRE_MHZ
    )


def _channels(layout: RfLayout, extent: SpectralExtent) -> tuple[int, ...]:
    if extent is SpectralExtent.BROADBAND:
        return tuple(channel.index for channel in layout.channels)
    return (_l1_index(layout),)


def _centre_sensor(layout: RfLayout, seed: int) -> str:
    """The receiver the incident is centred on, chosen from the seed.

    Receivers are sorted before indexing so the choice depends on the layout's
    contents rather than on the order they happen to appear in the file --
    otherwise editing the configuration silently restages every recorded run.
    """
    identifiers = sorted(site.sensor_id for site in layout.sensors)
    position = int(derive_unit(seed, "incident", "centre") * len(identifiers))
    return identifiers[min(position, len(identifiers) - 1)]


def plan_incident(layout: RfLayout, spec: RunSpec) -> Incident | None:
    """What this run stages, or None when it stages nothing.

    None rather than an empty incident: `normal-baseline` injects *nothing*,
    and an incident affecting no cells would still be a thing the emitter walks
    and a thing a reader has to check the emptiness of. The absence is the
    point, so it is represented as one.
    """
    scenario_type = ScenarioType(spec.scenario_type)
    if scenario_type not in _RF_TYPES:
        return None

    parameters = spec.incident
    centre = _centre_sensor(layout, spec.seed)
    if scenario_type in _SINGLE_SENSOR_TYPES:
        sensors: tuple[str, ...] = (centre,)
    else:
        # The centre and everything within the radius of it. `scn-005`
        # guarantees this is neither empty nor the whole layout, which is what
        # gives anom-005 something to discriminate.
        sensors = (centre, *layout.neighbours(centre, parameters.radius_km))

    start = spec.start + timedelta(seconds=parameters.start_offset_s)
    return Incident(
        sensors=tuple(sorted(sensors)),
        channels=_channels(layout, parameters.spectral_extent),
        start=start,
        end=start + timedelta(seconds=parameters.duration_s),
        elevation_db=parameters.elevation_db,
    )


def ground_truth(
    spec: RunSpec,
    incident: Incident | None,
    perturber: TrackPerturber | None = None,
) -> dict[str, Any]:
    """The answer key, for `scenario_runs.ground_truth`.

    Written for every run including the clean one, where it says that nothing
    was staged. An absent record and a record saying "nothing" are different
    claims, and only the second is evidence when the false-positive rate is
    computed (`anom-008`).

    Aircraft are named by pseudonym, never by source identifier. This record is
    stored in the database and is readable; a real aircraft address in it would
    reintroduce by the back door exactly what `dal-004` removes at the front.
    """
    scenario_type = ScenarioType(spec.scenario_type)
    return {
        "scenario_type": scenario_type.value,
        "seed": spec.seed,
        "spectral_extent": spec.incident.spectral_extent.value,
        "sensors": list(incident.sensors) if incident else [],
        "channels": list(incident.channels) if incident else [],
        "elevation_db": incident.elevation_db if incident else None,
        "window": (
            {"start": incident.start.isoformat(), "end": incident.end.isoformat()}
            if incident
            else None
        ),
        "track_mode": perturber.mode.value if perturber else None,
        "aircraft": sorted(perturber.affected) if perturber else [],
    }
