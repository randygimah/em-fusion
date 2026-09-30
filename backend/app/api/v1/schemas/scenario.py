"""Wire shapes for the scenario control endpoints. Spec: api-006.

Field names are camelCase and the class names match the interfaces in
`frontend/src/types/scenarioControl.ts`, as in `schemas/operational_picture.py`
-- with one deliberate exception. A run's **recorded parameters** are served
exactly as the run row holds them, snake_case included, because the generator
rebuilds a run from those names and refuses a set carrying one it does not
know. `backend/tests/test_scn_control_contract.py` holds both halves of that to
the contract.

`BatchRequest` is the odd one out and is not a wire shape at all: it is the
validated, domain-typed thing handed across the launcher seam, which is why it
carries an enum and an `IncidentParameters` rather than strings and numbers.
Putting it here keeps the route module to two handlers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.pipeline import DEFAULT_RUN_SECONDS, MAX_RUNS, MIN_RUNS
from app.scenario.incident import IncidentParameters, ScenarioType, SpectralExtent
from app.scenario.seeding import SEED_MAX


class ScenarioStartRequest(BaseModel):
    """Exactly the dials the batch entrypoint accepts, and nothing else.

    A control the generator has no input for would be a control that changes
    nothing, which is `scn-001`'s fourth failure case wearing a different hat.

    Every bound here is a 422 rather than a 500 later: an unknown scenario
    type, a batch outside the run bounds, and an incident that begins at or
    after the run ends are all refused before a single run row is opened.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenarioType: ScenarioType

    #: Null means *draw one*, never *invent one on the screen*. `scn-004`
    #: settled that a seed the run record never saw is a run nobody can repeat,
    #: so the value drawn here comes back in the response.
    baseSeed: int | None = Field(default=None, ge=0, le=SEED_MAX)

    runs: int = Field(default=MIN_RUNS, ge=MIN_RUNS, le=MAX_RUNS)
    durationSeconds: int = Field(default=DEFAULT_RUN_SECONDS, gt=0)
    incidentOffsetS: int = Field(default=120, ge=0)
    incidentDurationS: int = Field(default=300, gt=0)
    radiusKm: float = Field(default=60.0, gt=0.0)
    elevationDb: float = Field(default=8.0, gt=0.0)
    spectralExtent: SpectralExtent = SpectralExtent.NARROWBAND

    @model_validator(mode="after")
    def _the_incident_must_fall_inside_the_run(self) -> ScenarioStartRequest:
        """Refused here, not inside the background batch.

        `run_batch` raises on this too, and by then the request has already
        returned 202 and the refusal survives only in a log. It is the defect
        that produced twenty mislabelled controls: every run claiming a
        scenario type and containing no incident, with the command reporting
        success twenty times.
        """
        if (
            self.scenarioType is not ScenarioType.NORMAL_BASELINE
            and self.incidentOffsetS >= self.durationSeconds
        ):
            raise ValueError(
                f"an incident starting {self.incidentOffsetS} s into a "
                f"{self.durationSeconds} s run stages nothing: every run in "
                "this batch would claim a scenario type and contain no "
                "incident, which is a mislabelled control rather than a "
                "scenario."
            )
        return self

    def resolved(self, base_seed: int) -> BatchRequest:
        """The domain-typed batch this configuration describes."""
        return BatchRequest(
            scenario_type=self.scenarioType,
            base_seed=base_seed,
            runs=self.runs,
            duration_seconds=self.durationSeconds,
            incident=IncidentParameters(
                start_offset_s=self.incidentOffsetS,
                duration_s=self.incidentDurationS,
                radius_km=self.radiusKm,
                elevation_db=self.elevationDb,
                spectral_extent=self.spectralExtent,
            ),
        )


class BatchRequest(BaseModel):
    """What crosses the launcher seam. Spec: api-006.

    Validated and domain-typed, so a launcher never parses anything: the route
    has already turned five numbers and two strings into an enum and an
    `IncidentParameters`, and a launcher that had to do that itself would be a
    second place the dials are interpreted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_type: ScenarioType
    base_seed: int
    runs: int
    duration_seconds: int
    incident: IncidentParameters


class ScenarioStartAccepted(BaseModel):
    """What a caller gets back immediately. Spec: api-006 (third decision).

    An acceptance, not an outcome. The batch is about seventy seconds and the
    response arrives at once, so this is the only thing the caller receives
    synchronously -- which is why it carries the base seed actually used,
    including one the API drew, and every seed derived from it. Without them a
    caller would have to wait for rows to discover which seeds its own batch
    is running under.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseSeed: int
    runs: int
    seeds: list[int]


class BatchInFlight(BaseModel):
    """What is already running, when a start is refused. Spec: api-011.

    **Facts, never prose.** The sentence an analyst reads is composed on the
    screen, for two reasons. Every other piece of user-facing copy on that
    screen is already there -- the validation refusals, the acceptance note --
    so a server-composed message would split the screen's voice across two
    codebases and make its tone depend on the API. And a body of fields is
    assertable field by field, where a sentence is assertable only by substring,
    which is the weaker test of the two.

    Three fields and no fourth, and the suite asserts the key set exactly: what
    was *staged* is not here, per `api-009`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenarioType: str
    baseSeed: int
    startedAt: datetime


class ScenarioRunListing(BaseModel):
    """One row of the recent-runs table. Spec: api-006, scn-004.

    `completedAt` is null when the run is not known to have finished, which
    covers a run still going and a run that died. The row cannot tell them
    apart, so neither may the screen (`db-007`).

    There is no field for ground truth, and that is the point (`api-009`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    scenarioType: str
    seed: int
    startedAt: datetime
    completedAt: datetime | None
    parameters: dict[str, Any]
