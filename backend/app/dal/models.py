"""The canonical observation model. Spec: dal-001.

One model for every source (FR-101). Everything source-specific lives in
`payload`, typed per observation type, which is what keeps the canonical
shape stable as adapters are added -- the RQ1 extensibility claim made
concrete, and the reason `adp-003` should need no change here at all.

Three shapes are deliberately absent, each because its presence would
quietly undo a decision made elsewhere:

* No `icao24`, no `callsign`, under any name. `dal-004` replaces source
  aircraft identifiers with seeded pseudonyms, and its third failure case is
  retaining the source value beside the pseudonym. A model with nowhere to
  put one cannot fail that way. `TrackPayload.aircraft_id` is opaque by
  construction, so `dal-004` changes how it is *derived*, not this file.
* No WKT, WKB, or SRID on `Location` -- coordinates only. A storage-engine
  type here would mean the DAL knows about PostGIS, breaking the repository
  seam `db-003` requires before it is even built (`dal-002`).
* No ground truth, and no scenario *type*. `api-009` forbids it on any
  observation: a detector that can see the answer invalidates the campaign.

Every model is frozen. Validation runs before persistence, so a record that
has passed its check must not be editable past it afterwards.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataMode(str, Enum):
    """Replayed real telemetry, or generated under scenario control.

    Carried on every observation so the analyst-facing SYNTHETIC ENVIRONMENT
    DATA badge (`op-001`) reflects the data rather than a UI constant.
    """

    REPLAYED = "replayed"
    SYNTHETIC = "synthetic"


class SourceType(str, Enum):
    """The kind of source, not the instance -- that is `source_id`."""

    OPENSKY = "opensky"
    SYNTHETIC_RF = "synthetic_rf"


class ObservationType(str, Enum):
    """Selects the payload type. Adding a member is the adapter-facing half
    of adding a source; `PAYLOAD_TYPES` below is the other half."""

    TRACK = "track"
    RF = "rf"


class ValidationStatus(str, Enum):
    VALID = "valid"
    QUARANTINED = "quarantined"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Location(_Frozen):
    """A point on the earth, in degrees. Coordinates only -- see the module
    docstring on why no geometry type appears here."""

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class Provenance(_Frozen):
    """Where a record came from and under what run. Attached at the DAL and
    never by an adapter, so a new adapter cannot forget it (`dal-003`)."""

    source_id: str = Field(min_length=1)
    source_type: SourceType
    data_mode: DataMode
    scenario_run_id: int


class TrackPayload(_Frozen):
    """Aircraft state. `aircraft_id` is a pseudonym, opaque by contract.

    `position_staleness_s` is the measured delta between the state vector's
    time and its `lastposupdate` -- a directly reported field rather than an
    inferred one, and the basis of the update-frequency rule.
    """

    aircraft_id: str = Field(min_length=1)
    altitude_m: float | None = None
    velocity_ms: float | None = None
    heading_deg: float | None = None
    vertical_rate_ms: float | None = None
    on_ground: bool
    position_staleness_s: float


class RfPayload(_Frozen):
    """One reading from one sensor on one channel (`scn-005`).

    Emitted on a dense sensor x channel x time grid, so a missing reading is
    a detectable gap rather than an ambiguous absence.
    """

    sensor_id: str = Field(min_length=1)
    channel_index: int = Field(ge=0)
    centre_frequency_mhz: float = Field(gt=0.0)
    band: str = Field(min_length=1)
    power_dbm: float
    snr_db: float
    bandwidth_mhz: float = Field(gt=0.0)
    signal_type: str = Field(min_length=1)
    baseline_delta_db: float


Payload = TrackPayload | RfPayload

#: The observation type to payload type mapping, in one place. A third
#: adapter registers here; nothing else in the DAL changes.
PAYLOAD_TYPES: dict[ObservationType, type[Payload]] = {
    ObservationType.TRACK: TrackPayload,
    ObservationType.RF: RfPayload,
}


class CanonicalObservation(_Frozen):
    """What every adapter's output becomes, whatever the source."""

    source_id: str = Field(min_length=1)
    source_type: SourceType
    observation_type: ObservationType
    timestamp: datetime
    location: Location
    data_mode: DataMode
    validation_status: ValidationStatus
    provenance: Provenance
    payload: Payload

    @model_validator(mode="after")
    def _payload_matches_observation_type(self) -> CanonicalObservation:
        """A track observation carrying an RF payload is not a track
        observation. The union alone would accept either, so the constraint
        is asserted on the model rather than trusted to the caller."""
        expected = PAYLOAD_TYPES[self.observation_type]
        if type(self.payload) is not expected:
            raise ValueError(
                f"{self.observation_type.value} observation requires "
                f"{expected.__name__}, got {type(self.payload).__name__}"
            )
        return self
