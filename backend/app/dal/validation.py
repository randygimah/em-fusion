"""Required-field validation, ahead of persistence. Spec: dal-001.

The entrypoint every adapter goes through. It returns an outcome rather than
raising, because `dal-002` requires that one bad record never aborts an
ingest run -- a batch of ten with three invalid must yield seven
observations and three quarantine rows and complete quietly.

A rejection names the field that failed and why. That is not a courtesy: it
is what `dal-002` writes to quarantine, and a quarantine row that cannot say
what was wrong with the record is a silent drop with extra steps.

Nothing here writes anything. Where an accepted observation goes is
`dal-002`'s repository port; whether the schema would also have refused a
bad one is `db-001`'s NOT NULL constraints, asserted there and not here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.dal.models import (
    PAYLOAD_TYPES,
    CanonicalObservation,
    DataMode,
    Location,
    ObservationType,
    Provenance,
    SourceType,
    ValidationStatus,
)
from app.dal.pseudonymise import IdentifierError, Pseudonymiser, substitute

#: Top-level fields an adapter must supply. Provenance is not among them:
#: the DAL attaches it from the ingest context, which is the whole point of
#: `dal-003`.
REQUIRED_FIELDS = (
    "source_id",
    "source_type",
    "observation_type",
    "timestamp",
    "location",
    "payload",
)


class IngestContext(BaseModel):
    """What the DAL knows about the run, rather than about the record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_mode: DataMode
    scenario_run_id: int


class Rejection(BaseModel):
    """Why a record did not become an observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    reason: str


class ValidationOutcome(BaseModel):
    """Exactly one of `observation` and `rejection` is set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation: CanonicalObservation | None = None
    rejection: Rejection | None = None

    @property
    def accepted(self) -> bool:
        return self.observation is not None


def _accept(observation: CanonicalObservation) -> ValidationOutcome:
    return ValidationOutcome(observation=observation)


def _reject(field: str, reason: str) -> ValidationOutcome:
    return ValidationOutcome(rejection=Rejection(field=field, reason=reason))


def _first_error(error: ValidationError) -> tuple[str, str]:
    """The failing sub-path and message from a Pydantic error."""
    first = error.errors()[0]
    path = ".".join(str(part) for part in first["loc"])
    return path, str(first["msg"])


def validate_record(
    record: Mapping[str, Any],
    context: IngestContext,
    pseudonymiser: Pseudonymiser,
) -> ValidationOutcome:
    """Turn one source record into a canonical observation, or say why not.

    Validated in stages rather than in a single Pydantic pass, because the
    payload's type is not known until `observation_type` has been read, and
    because a rejection has to name one field -- an aggregated error over a
    half-resolved model names none of them usefully.
    """
    # Checked before the required fields, so an adapter doing the DAL's job
    # is reported as itself rather than masked by whatever else is wrong with
    # the record. Attachment at the DAL is only a guarantee if the DAL is the
    # sole source of it (`dal-003`).
    if "provenance" in record:
        return _reject(
            "provenance",
            "provenance is attached by the DAL, not supplied by an adapter",
        )

    for field in REQUIRED_FIELDS:
        if record.get(field) is None:
            return _reject(field, f"{field} is required and was not supplied")

    try:
        observation_type = ObservationType(record["observation_type"])
    except ValueError:
        return _reject(
            "observation_type",
            f"{record['observation_type']!r} is not a known observation type",
        )

    try:
        source_type = SourceType(record["source_type"])
    except ValueError:
        return _reject(
            "source_type", f"{record['source_type']!r} is not a known source type"
        )

    try:
        location = Location.model_validate(record["location"])
    except ValidationError as error:
        path, message = _first_error(error)
        return _reject("location", f"{path}: {message}" if path else message)

    # Identifiers are substituted before the payload is validated, so no
    # model in the DAL is ever constructed holding a real one (`dal-004`).
    try:
        payload_source = substitute(observation_type, record["payload"], pseudonymiser)
    except IdentifierError as error:
        return _reject(error.field, error.reason)

    payload_type = PAYLOAD_TYPES[observation_type]
    try:
        payload = payload_type.model_validate(payload_source)
    except ValidationError as error:
        path, message = _first_error(error)
        return _reject(f"payload.{path}" if path else "payload", message)

    provenance = Provenance(
        source_id=record["source_id"],
        source_type=source_type,
        data_mode=context.data_mode,
        scenario_run_id=context.scenario_run_id,
    )

    try:
        observation = CanonicalObservation(
            source_id=record["source_id"],
            source_type=source_type,
            observation_type=observation_type,
            timestamp=record["timestamp"],
            location=location,
            data_mode=context.data_mode,
            validation_status=ValidationStatus.VALID,
            provenance=provenance,
            payload=payload,
        )
    except ValidationError as error:
        path, message = _first_error(error)
        return _reject(path or "observation", message)

    return _accept(observation)
