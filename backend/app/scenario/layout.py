"""The RF sensor and channel layout. Spec: scn-005.

The fixed geometry of the synthetic RF side: seven sensors at recorded
positions, eight 2 MHz channels centred on the GNSS L1 band, and one reading
per sensor per channel per interval of simulated time. What varies per run --
noise amplitude, which sensors are affected, when an event starts -- is
`scn-002`'s business, and deliberately has no field here.

**This is configuration, not constants.** The layout is a JSON document that
`load_layout` reads and validates; `DEFAULT_LAYOUT_PATH` is the one shipped
with the package so a fresh clone runs with no mount and no environment
variable, and any other path may be passed instead. Nothing that consumes a
layout -- the generator, the adapter, or any Phase 6 detector -- may hold a
sensor position or a centre frequency of its own (FR-109).

Three properties are enforced at load, because each one is a silent
wrong-answer bug rather than a crash if it reaches the detectors:

* **Adjacency by index is adjacency in frequency.** Indices run contiguously
  from zero and centres strictly ascend, so `anom-007`'s frequency-neighbour
  test compares channels that really are neighbours.
* **Exactly one channel is centred on L1, and it is not at either end of the
  plan.** L1 is the band `gnss-degradation` targets, and adjacency has to run
  in both directions from it. The shipped plan has four channels below and
  three above -- an earlier wording of the spec said "four either side", which
  needs nine channels rather than eight.
* **The layout discriminates at its recorded radius.** FR-109 asks that "a
  candidate interference zone contains some sensors and excludes others",
  which is prose rather than a check. It is enforced here as two invariants:
  every sensor has at least one other *within* the radius, or `anom-007` has
  no neighbour to compare it against; and at least one *beyond* it, or every
  zone contains the whole layout and `anom-005` cannot discriminate. A layout
  failing either is rejected at load rather than accepted and diagnosed six
  phases later, when the symptom would be an unexplained detection rate.

Distances are great-circle, computed here rather than by PostGIS, because a
layout is validated before any database connection exists and before any
observation has been written. The scale is tens of kilometres over a region
five degrees tall, where a spherical earth is accurate to well under the
precision any of these decisions turns on.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

#: GNSS L1, in MHz. One channel sits exactly here; see the module docstring.
L1_CENTRE_MHZ = 1575.42

#: Eight channels (FR-108). Fewer stops supporting the narrowband-versus-
#: broadband distinction that makes spectral extent a scenario parameter
#: rather than a sixth scenario type.
CHANNEL_COUNT = 8

#: Six to eight sensors (FR-108). Below six, "neighbouring sensors stayed
#: nominal" and spatial clustering are barely claims worth testing.
MIN_SENSORS = 6
MAX_SENSORS = 8

#: Mean earth radius, IUGG. Fixed here so a distance is reproducible rather
#: than dependent on whichever constant a caller happened to use.
EARTH_RADIUS_KM = 6371.0088

#: The layout shipped with the package.
DEFAULT_LAYOUT_PATH = Path(__file__).with_name("rf_layout.json")


class LayoutError(ValueError):
    """A layout could not be read, parsed, or validated.

    One exception type for all three, because every caller does the same thing
    with them: refuse to start. A generator that ran against a half-valid
    layout would emit observations no detector could interpret.
    """


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SensorSite(_Frozen):
    """One RF sensor, at a fixed position. `station_name` is for the analyst;
    `sensor_id` is what every observation and anomaly refers to."""

    sensor_id: str = Field(min_length=1)
    station_name: str = Field(min_length=1)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class Channel(_Frozen):
    """One channel of the plan. `band` names the band the channel falls in,
    which is not the same as being centred on it -- all eight sit inside the
    L1 band and exactly one is centred on L1 itself."""

    index: int = Field(ge=0)
    centre_frequency_mhz: float = Field(gt=0.0)
    bandwidth_mhz: float = Field(gt=0.0)
    band: str = Field(min_length=1)


class RfLayout(_Frozen):
    """The validated layout, and the only interface Phase 6 needs to it."""

    sensors: tuple[SensorSite, ...]
    channels: tuple[Channel, ...]
    interval_seconds: int = Field(gt=0)
    discrimination_radius_km: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _sensors_are_distinct(self) -> RfLayout:
        if not MIN_SENSORS <= len(self.sensors) <= MAX_SENSORS:
            raise ValueError(
                f"a layout needs {MIN_SENSORS} to {MAX_SENSORS} sensors, "
                f"got {len(self.sensors)}"
            )
        identifiers = [s.sensor_id for s in self.sensors]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("sensor identifiers must be unique")
        positions = [(s.lat, s.lon) for s in self.sensors]
        if len(set(positions)) != len(positions):
            raise ValueError(
                "two sensors at one position are one sensor counted twice in "
                "any spatial cluster"
            )
        return self

    @model_validator(mode="after")
    def _channel_plan_is_coherent(self) -> RfLayout:
        if len(self.channels) != CHANNEL_COUNT:
            raise ValueError(
                f"the channel plan has {CHANNEL_COUNT} channels, "
                f"got {len(self.channels)}"
            )
        indices = [c.index for c in self.channels]
        if indices != list(range(len(self.channels))):
            raise ValueError(
                "channel indices must run contiguously from zero, so that "
                f"adjacency by index is adjacency in frequency; got {indices}"
            )
        centres = [c.centre_frequency_mhz for c in self.channels]
        if any(b <= a for a, b in zip(centres, centres[1:])):
            raise ValueError(
                f"centre frequencies must strictly ascend with index; got {centres}"
            )
        on_l1 = [
            c.index for c in self.channels if c.centre_frequency_mhz == L1_CENTRE_MHZ
        ]
        if len(on_l1) != 1:
            raise ValueError(
                f"exactly one channel must be centred on GNSS L1 "
                f"({L1_CENTRE_MHZ} MHz); {len(on_l1)} are"
            )
        if on_l1[0] in (0, len(self.channels) - 1):
            raise ValueError(
                "the L1 channel must have a channel on each side, so frequency "
                f"adjacency runs in both directions; it is at index {on_l1[0]}"
            )
        return self

    @model_validator(mode="after")
    def _layout_discriminates(self) -> RfLayout:
        radius = self.discrimination_radius_km
        for site in self.sensors:
            distances = [
                _haversine_km(site.lat, site.lon, other.lat, other.lon)
                for other in self.sensors
                if other.sensor_id != site.sensor_id
            ]
            if not any(d <= radius for d in distances):
                raise ValueError(
                    f"{site.sensor_id} has no sensor within "
                    f"{radius} km, so a neighbour test on it compares nothing"
                )
            if not any(d > radius for d in distances):
                raise ValueError(
                    f"{site.sensor_id} has no sensor beyond {radius} km, so a "
                    "zone centred on it contains the whole layout and spatial "
                    "clustering cannot discriminate"
                )
        return self

    def _site(self, sensor_id: str) -> SensorSite:
        for site in self.sensors:
            if site.sensor_id == sensor_id:
                return site
        raise KeyError(f"no sensor {sensor_id!r} in this layout")

    def distance_km(self, sensor_id: str, other_id: str) -> float:
        """Great-circle distance between two sensors, in kilometres."""
        a, b = self._site(sensor_id), self._site(other_id)
        return _haversine_km(a.lat, a.lon, b.lat, b.lon)

    def neighbours(
        self, sensor_id: str, radius_km: float | None = None
    ) -> tuple[str, ...]:
        """The other sensors within the radius, nearest first.

        `anom-007` compares a sensor against these; a sensor is never its own
        neighbour, and an unknown identifier is a caller bug rather than an
        empty result, which would read as "no neighbours" and quietly turn the
        neighbour test into a pass.
        """
        origin = self._site(sensor_id)
        limit = self.discrimination_radius_km if radius_km is None else radius_km
        ranked = sorted(
            (
                (
                    _haversine_km(origin.lat, origin.lon, other.lat, other.lon),
                    other.sensor_id,
                )
                for other in self.sensors
                if other.sensor_id != sensor_id
            )
        )
        return tuple(identifier for distance, identifier in ranked if distance <= limit)

    def adjacent_channels(self, index: int) -> tuple[int, ...]:
        """The channel indices either side of `index`, ascending.

        One entry at each end of the plan and two in the middle. `anom-007`
        reads this as its frequency-neighbour test: a real emission raises
        adjacent channels together, so a lone deviation with clean neighbours
        is evidence about the sensor rather than the environment.
        """
        if not any(channel.index == index for channel in self.channels):
            raise KeyError(f"no channel {index} in this plan")
        return tuple(c.index for c in self.channels if abs(c.index - index) == 1)


def load_layout(path: Path | None = None) -> RfLayout:
    """Read and validate a layout, or the packaged default.

    Fails loudly and names the file: a missing or malformed layout must stop
    the run before any observation is generated, since every alternative --
    a default layout, a partial one, an empty one -- produces a stream that
    looks plausible and means nothing.
    """
    source = DEFAULT_LAYOUT_PATH if path is None else Path(path)
    try:
        text = source.read_text()
    except OSError as error:
        raise LayoutError(f"RF layout could not be read: {source} ({error})") from error
    try:
        document: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise LayoutError(f"RF layout is not valid JSON: {source} ({error})") from error
    try:
        return RfLayout.model_validate(document)
    except ValidationError as error:
        raise LayoutError(f"RF layout is invalid: {source}\n{error}") from error
