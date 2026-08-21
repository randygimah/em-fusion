"""Ingest a batch: accept, quarantine, attach provenance. Spec: dal-002, dal-003.

The single entrypoint every adapter goes through, which is what makes the
two guarantees below properties of the architecture rather than of any
adapter's diligence:

* **Nothing is silently dropped.** Every record in the batch leaves as
  either an observation or a quarantine record, and the counts of both are
  returned. A record that fails validation does not abort the run -- an
  ingest that stops at the first malformed row is not usable against a real
  corpus, where 500 of the retained OpenSky rows have no position at all.
* **Provenance is attached here, not per adapter** (`dal-003`). A new
  adapter inherits it without its author having to know it exists, which is
  the same argument `dal-004` makes for pseudonymisation one field over.

Persistence is one call on the repository port, so the observations and the
quarantine records of a run commit together or not at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.dal.models import CanonicalObservation
from app.dal.repository import ObservationRepository, QuarantineRecord
from app.dal.validation import IngestContext, Rejection, validate_record


class IngestResult(BaseModel):
    """What one run did. The per-run count `dal-002` requires."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: int
    quarantined: int


def _text(value: Any) -> str | None:
    """Best-effort attribution from a record that may be malformed.

    `str()` on a `(str, Enum)` member renders as `SourceType.OPENSKY` rather
    than as its value, which would put the Python identifier into a
    quarantine row instead of the source's own name for itself.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _quarantine(
    record: Mapping[str, Any], rejection: Rejection, context: IngestContext
) -> QuarantineRecord:
    return QuarantineRecord(
        source_id=_text(record.get("source_id")),
        source_type=_text(record.get("source_type")),
        observation_type=_text(record.get("observation_type")),
        scenario_run_id=context.scenario_run_id,
        field=rejection.field,
        reason=rejection.reason,
    )


def ingest_batch(
    records: Iterable[Mapping[str, Any]],
    context: IngestContext,
    repository: ObservationRepository,
) -> IngestResult:
    """Validate a batch, persist both halves of it, and report the counts."""
    observations: list[CanonicalObservation] = []
    quarantined: list[QuarantineRecord] = []

    for record in records:
        outcome = validate_record(record, context)
        if outcome.observation is not None:
            observations.append(outcome.observation)
        else:
            # `validate_record` sets exactly one of the two; a rejection
            # without a reason would be the silent drop this exists to stop.
            assert outcome.rejection is not None
            quarantined.append(_quarantine(record, outcome.rejection, context))

    if observations or quarantined:
        repository.save_batch(observations, quarantined)

    return IngestResult(accepted=len(observations), quarantined=len(quarantined))
