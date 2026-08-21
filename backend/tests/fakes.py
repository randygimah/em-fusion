"""In-memory implementations of the DAL's ports, for tests.

A fake rather than a mock: it has real behaviour and can be asserted
against, which is what lets `dal-002` be proven without a database. The
PostGIS implementation of the same protocol lands with `db-001`; both are
held to that protocol, so what is asserted here is DAL behaviour and not the
storage engine's.

Reused beyond dal-002 -- the detectors, the evidence bundle builder, and the
grounding check all need canonical observations without a live database.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.dal.models import CanonicalObservation
from app.dal.repository import QuarantineRecord


class InMemoryObservationRepository:
    """Holds what a run wrote, and counts how many times it was asked to."""

    def __init__(self) -> None:
        self.observations: list[CanonicalObservation] = []
        self.quarantined: list[QuarantineRecord] = []
        self.calls = 0

    def save_batch(
        self,
        observations: Sequence[CanonicalObservation],
        quarantined: Sequence[QuarantineRecord],
    ) -> None:
        self.calls += 1
        self.observations.extend(observations)
        self.quarantined.extend(quarantined)


class FailingObservationRepository(InMemoryObservationRepository):
    """Refuses the write, so the all-or-nothing guarantee can be exercised."""

    def save_batch(
        self,
        observations: Sequence[CanonicalObservation],
        quarantined: Sequence[QuarantineRecord],
    ) -> None:
        self.calls += 1
        raise RuntimeError("the database is not having it")
