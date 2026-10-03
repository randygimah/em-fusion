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
from typing import Any

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
    """Aircraft state. `aircraft_id` and `flight_id` are pseudonyms, derived
    by the DAL from `icao24` and `callsign` and opaque by contract; the source
    values never reach this model (`dal-004`). `flight_id` is optional because
    OpenSky reports many blank callsigns, and a blank one is missing data
    rather than an identity.

    The two staleness fields are different measurements, and keeping them
    apart is what lets the detectors tell two scenario types apart.
    `position_staleness_s` is `time - lastposupdate`, the age of the
    coordinate carried inside the row; `contact_staleness_s` is
    `time - lastcontact`, the interval since any message was received. Both
    are directly reported deltas rather than inferred values.

    Both stale means the aircraft is no longer heard from -- a coverage gap.
    Fresh contact with a stale position means it is still transmitting while
    its position has stopped advancing, which is the GNSS-degradation
    signature. 4,553 rows of the current extract (3.4%) carry the second
    shape, so this is a real discriminator rather than a theoretical one.

    Both are required. `lastcontact` is present on every one of the extract's
    133,634 rows, `lastposupdate` on all but the 500 with no position -- rows
    that quarantine on the position anyway.
    """

    aircraft_id: str = Field(min_length=1)
    flight_id: str | None = None
    altitude_m: float | None = None
    velocity_ms: float | None = None
    heading_deg: float | None = None
    vertical_rate_ms: float | None = None
    on_ground: bool
    position_staleness_s: float
    contact_staleness_s: float


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


class ScenarioRunSummary(BaseModel):
    """What a run is, to anything that reads one back. Spec: api-002.

    Deliberately not every column of `scenario_runs`. **There is no field for
    ground truth**, because `api-009` requires the answer key never to leave the
    run record and a model that cannot hold it cannot leak it on any run — a
    stronger guarantee than remembering to strip it at each call site, and one a
    test can assert once rather than per endpoint.

    `completed_at` is carried because absence is the informative state
    (`db-007`): a reader choosing between two runs needs to know which one is
    known to have finished.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    scenario_type: str
    seed: int
    started_at: datetime
    completed_at: datetime | None


class DetectionPass(BaseModel):
    """That a run was examined, when, and under what settings. Spec: anom-015.

    **A separate object rather than two more fields on `ScenarioRunSummary`**,
    and for `ScenarioRunDetail`'s reason in reverse. The summary is served on
    the operational picture, and this is read there too -- but it is read as an
    *answer to a different question*, "has anything looked at this run", which
    `api-012` turns into the presence or absence of a whole section of the
    payload. Carried on the summary it would also travel to `/scenario/runs`,
    where `api-006` serves a contract that does not ask for it.

    The value of this type is that it **cannot exist for a run nothing
    examined**. A nullable pair of fields on the summary makes a stamp without
    its policy, and a policy without its stamp, both representable -- and the
    second is a run claiming settings for an examination that never happened.

    `at` is the **database's** clock, written by `now()` where the row is
    stamped, following `complete_scenario_run`: when something happened to a run
    is one clock's to keep, or two producers on two machines write times that
    cannot be ordered against each other.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_run_id: int
    at: datetime
    #: `eval-003`'s vocabulary verbatim, as `anom-015` records it. Required: a
    #: pass with no settings recorded is the unprovenanced state, and that state
    #: is the *absence of this object*, not an empty mapping inside one.
    policy: dict[str, str]


class ScenarioRunDetail(ScenarioRunSummary):
    """A run as the Scenario Control screen lists it. Spec: api-006.

    The summary's fields plus the parameters a replay cannot do without.

    **A subclass rather than two more fields on `ScenarioRunSummary`**, because
    `api-002` serves the summary as well. The recorded parameters carry the
    incident's radius, elevation, offset and duration, and putting those on the
    operational picture would describe the staged incident to the analyst whose
    detectors are being measured against it.

    Still no field for ground truth, for `api-009`'s reason: a shape that
    cannot hold the answer key cannot leak it.
    """

    #: Served exactly as the run row holds them, snake_case included. The
    #: generator rebuilds a run from these names and refuses a set carrying one
    #: it does not know, so a re-keying here would turn a replayable run into
    #: an unreplayable one at the point furthest from the mistake.
    parameters: dict[str, Any]


class SelectableRun(BaseModel):
    """One hour the operational picture will serve, as a chooser needs it.

    Spec: `api-013`. Four fields, and the item is mostly about the fields that
    are **not** here.

    **No scenario type**, following `ScenarioRunSummary`'s own argument one
    step further: a shape with no field for the answer cannot leak it on any
    run, which is stronger than remembering to strip it per endpoint
    (`api-009`). `/api/v1/scenario/runs` serves a very similar list and does
    carry the type -- legitimately, Scenario Control being the harness's own
    face -- and this model exists because that same string is disqualifying on
    the analyst's screen. `api-012` found it in that screen's heading after a
    year, and it survived because a search of the whole repository for it finds
    a justified use and stops.

    **Nothing the detectors concluded**: no finding count, no severity, no
    claim type. Not for `api-009`'s reason -- a detector's conclusion is
    precisely what an analyst is meant to see, and is served in full for the
    hour actually selected -- but because on this corpus precision is 1.000 and
    recall is 60 of 60 on every positive arm, so a count of reportable findings
    is empirically a near-perfect proxy for whether anything was staged. An
    hour chooser ranked by it would make any later exercise in which a person
    reads this screen un-blind, with nothing in the code saying so, and
    `eval-006` is still outstanding.

    **The window is the replayed hour and may be absent.** It comes from what
    the run row records of its own simulated start and length, and a replay run
    records neither -- so an hour that cannot name itself says so. The
    alternative is the failure case: `started_at` is the wall-clock minute the
    generator ran, and labelling a replayed 2022 hour with it is `anom-009`'s
    recorded mistake, wall clock in a simulated-time costume.

    **Examined is carried**, and it is a different kind of fact from what was
    found: whether anybody looked is answered by the presence of `anom-015`'s
    run stamp and never by a number in it (`api-012`). Carrying it means
    selecting an hour nothing has examined is not a surprise after the fact.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: int
    observed_from: datetime | None
    observed_to: datetime | None
    examined: bool
