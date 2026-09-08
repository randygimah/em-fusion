"""The baseline RF emitter, and the run it is emitted for. Spec: scn-001.

`scn-001` is a property -- same type, parameters and seed give a byte-identical
stream -- and a property needs something to hold over. This is the smallest
emitter that has anything to be deterministic about: one reading per sensor per
channel per interval of `scn-005`'s layout, at a nominal noise floor with
seeded per-cell variation and nothing injected.

**Deliberately not a scenario type.** `scn-002` owns the five types and the
ground-truth record that makes them scorable; `adp-002` owns wiring this stream
through the DAL into the store. What is here is the substrate both of those
build on, which is why `RunSpec.scenario_type` is carried but never read: the
value belongs on the run record, and the moment an emitter branches on it, the
generator can see the answer key.

**Nothing here reads a clock.** Time is `spec.start` plus a whole number of
layout intervals -- simulated time, not elapsed time -- so a run emitted today
and the same run emitted next year are the same bytes. The only wall-clock
timestamp in a run is `scenario_runs.started_at`, which is the database's and
describes the run rather than the data.

**Readings are rounded to a hundredth of a decibel.** Two reasons, and the
second is the load-bearing one: 0.01 dB is far below any threshold a detector
will use, and rounding puts the last bits of `log` and `cos` -- the one part of
the derivation whose final ulp is a property of the platform's libm rather than
of the arithmetic -- underneath the value that gets serialised. Byte-identity
across machines is then a property of the code rather than a hope about
floating point.

The record shape is the DAL's source-record shape, the same one
`app/adapters/opensky.py` produces: no provenance, no `data_mode`, no
`scenario_run_id`, because those describe the run and arrive through
`IngestContext` (`dal-003`). No scenario type and no ground truth either, per
`api-009`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.dal.models import ObservationType, SourceType
from app.scenario.incident import Incident, IncidentParameters, ScenarioType
from app.scenario.layout import Channel, RfLayout, SensorSite
from app.scenario.seeding import derive_gaussian, new_seed

#: What this source calls itself, in every record it emits. One value, so a
#: query for synthetic RF does not have to know which run wrote it.
SOURCE_ID = "synthetic-rf"

#: The baseline carries no emitter, so what a sensor reports is the noise
#: floor. `scn-002` introduces the signal types an injected event produces.
SIGNAL_TYPE_NOISE = "noise"

#: Hundredths of a decibel; see the module docstring on why this is not
#: cosmetic.
_DECIMALS = 2


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BaselineParameters(_Frozen):
    """What varies between two baseline runs of the same seed.

    Three numbers, and each has to change the stream or it is not a parameter.
    `noise_sigma_db` is the per-cell spread the Phase 8 baseline engine will
    average over; the two nominals are what it averages towards.
    """

    nominal_power_dbm: float = -95.0
    noise_sigma_db: float = Field(default=1.5, ge=0.0)
    nominal_snr_db: float = 20.0


class RunSpec(_Frozen):
    """A run, fully described: the three inputs plus the span to emit over.

    Frozen, because a spec that can be edited after a run has started is a run
    whose recorded parameters describe something other than what was emitted.
    """

    scenario_type: ScenarioType
    parameters: BaselineParameters
    #: What this run stages, if it stages anything. Carried even for
    #: `normal-baseline`, because `ground_truth` records the spectral extent a
    #: run was configured with whether or not it used it -- a batch varying one
    #: parameter should say so on every row, including the control.
    incident: IncidentParameters = IncidentParameters()
    seed: int = Field(ge=0)
    start: datetime
    duration_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def _start_is_absolute(self) -> RunSpec:
        """A naive start is a start in whichever timezone the machine is in,
        which makes the same run emit different timestamps in two places."""
        if self.start.tzinfo is None:
            raise ValueError(
                "start must carry a timezone: a naive timestamp reproduces "
                "differently on a machine in another zone"
            )
        return self

    @classmethod
    def create(
        cls,
        *,
        scenario_type: ScenarioType | str,
        start: datetime,
        duration_seconds: int,
        parameters: BaselineParameters | None = None,
        incident: IncidentParameters | None = None,
        seed: int | None = None,
    ) -> RunSpec:
        """Build a spec, drawing a seed if none was supplied.

        The one place a seed may be generated, and it is generated *into* the
        spec -- which is what the run record is written from -- so a run can
        never be emitted under a seed nobody recorded.
        """
        return cls(
            scenario_type=ScenarioType(scenario_type),
            parameters=BaselineParameters() if parameters is None else parameters,
            incident=IncidentParameters() if incident is None else incident,
            seed=new_seed() if seed is None else seed,
            start=start,
            duration_seconds=duration_seconds,
        )

    def as_parameters(self) -> dict[str, Any]:
        """The parameter set as it goes onto the run row.

        The seed is not in here: it has a column of its own, and a value stored
        twice is a value that can disagree with itself.
        """
        return {**self.parameters.model_dump(), **self.incident.model_dump()}


def ticks(layout: RfLayout, spec: RunSpec) -> tuple[datetime, ...]:
    """The simulated instants the grid reports at.

    Half-open on the duration, so a sixty-second run at a ten-second interval
    is six ticks rather than seven, and two consecutive runs tile without
    reporting the same instant twice.
    """
    steps = -(-spec.duration_seconds // layout.interval_seconds)
    return tuple(
        spec.start + timedelta(seconds=step * layout.interval_seconds)
        for step in range(steps)
    )


def _injection_db(
    spec: RunSpec,
    incident: Incident | None,
    sensor: SensorSite,
    channel: Channel,
    tick: int,
    timestamp: datetime,
) -> float:
    """How much this cell's floor is raised, in decibels. Zero for most cells.

    Derived under its own key -- `"injection"` rather than `"noise"` -- which is
    what keeps `scn-001`'s guarantee intact: the noise value for a cell is
    computed from the same inputs whether or not anything is staged, so adding
    an incident cannot move a reading the incident does not touch. Under a
    sequential generator this would be impossible, because the extra draw would
    shift everything after it.

    The magnitude varies per cell rather than being a flat step. A perfectly
    uniform elevation across a zone is not what interference looks like, and a
    detector tuned against it would be tuned against an artefact of the
    generator.
    """
    if incident is None or not incident.touches(
        sensor.sensor_id, channel.index, timestamp
    ):
        return 0.0
    spread = 1.0 + 0.25 * derive_gaussian(
        spec.seed, sensor.sensor_id, channel.index, tick, "injection"
    )
    return incident.elevation_db * max(spread, 0.0)


def _reading(
    spec: RunSpec,
    sensor: SensorSite,
    channel: Channel,
    tick: int,
    timestamp: datetime,
    incident: Incident | None,
) -> dict[str, Any]:
    parameters = spec.parameters
    noise_db = round(
        parameters.noise_sigma_db
        * derive_gaussian(spec.seed, sensor.sensor_id, channel.index, tick, "noise")
        + _injection_db(spec, incident, sensor, channel, tick, timestamp),
        _DECIMALS,
    )
    return {
        "sensor_id": sensor.sensor_id,
        "channel_index": channel.index,
        "centre_frequency_mhz": channel.centre_frequency_mhz,
        "band": channel.band,
        "power_dbm": round(parameters.nominal_power_dbm + noise_db, _DECIMALS),
        # A noisier channel is a worse channel: the same deviation that raises
        # the floor is what a signal has to be heard over.
        "snr_db": round(parameters.nominal_snr_db - noise_db, _DECIMALS),
        "bandwidth_mhz": channel.bandwidth_mhz,
        "signal_type": SIGNAL_TYPE_NOISE,
        # At baseline this *is* the noise, which is what makes it the field an
        # injected event moves.
        "baseline_delta_db": noise_db,
    }


def emit_rf(
    layout: RfLayout, spec: RunSpec, incident: Incident | None = None
) -> tuple[dict[str, Any], ...]:
    """The whole run, as source records, in a fixed order.

    Dense by construction: every sensor reports every channel at every tick, so
    a missing reading downstream is a detectable gap rather than an ambiguous
    absence (`adp-002`).

    Materialised rather than yielded. The stream is the unit `scn-001` makes a
    claim about, a caller that consumed half a generator would hold half a
    claim, and an hour of the shipped layout is 20,160 records.

    The order is time, then sensor identifier, then channel index -- sorted
    here rather than taken from the layout file, because byte-identity is a
    claim about a sequence and a reordered configuration file must not change
    it. Derivation itself is order-independent (`seeding.py`), so this decides
    only how the records are arranged, never what they contain.
    """
    sensors = sorted(layout.sensors, key=lambda site: site.sensor_id)
    channels = sorted(layout.channels, key=lambda channel: channel.index)

    return tuple(
        {
            "source_id": SOURCE_ID,
            "source_type": SourceType.SYNTHETIC_RF,
            "observation_type": ObservationType.RF,
            "timestamp": timestamp,
            "location": {"lat": sensor.lat, "lon": sensor.lon},
            "payload": _reading(spec, sensor, channel, tick, timestamp, incident),
        }
        for tick, timestamp in enumerate(ticks(layout, spec))
        for sensor in sensors
        for channel in channels
    )


def emit_baseline(layout: RfLayout, spec: RunSpec) -> tuple[dict[str, Any], ...]:
    """The same run with nothing staged in it.

    Kept as a name of its own rather than folded into a default argument,
    because `scn-002` asks for it explicitly: "the quiet run for this seed" is
    what an injected run is compared against to prove the injection added
    rather than moved.
    """
    return emit_rf(layout, spec, None)


def _plain(value: object) -> str:
    """Anything JSON cannot render on its own. Enum members need no entry:
    every enum in the DAL subclasses `str`, so they serialise as their values."""
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} has no canonical serialisation")


def stream_digest(records: Iterable[Mapping[str, Any]]) -> str:
    """A SHA-256 over the stream's canonical serialisation.

    "Byte-identical" needs one definition of the bytes, and this is it: keys
    sorted so a dictionary's insertion order cannot show through, separators
    fixed so whitespace cannot, record order preserved because the order *is*
    part of the claim.

    Returned rather than compared, so a digest can go into a run record, a
    thesis table, or a batch's reproducibility check without any of them
    holding the stream itself.
    """
    canonical = json.dumps(
        list(records), sort_keys=True, separators=(",", ":"), default=_plain
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
