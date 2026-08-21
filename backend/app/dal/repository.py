"""The DAL's persistence port. Spec: dal-002.

An interface, not an implementation. The DAL hands it canonical
observations and quarantine records; what happens to them is the storage
layer's business. `db-003` requires this seam whatever the build order, so
defining it before the database exists adds a second implementation rather
than a second layer -- the in-memory one in `tests/fakes.py` now, the
PostGIS one with `db-001` later.

Two properties of the signature are load-bearing:

* **No storage-engine type crosses it.** No session, no engine, no WKT or
  WKB string, no caller-supplied primary key. A geometry type here would
  mean the DAL knows about PostGIS, which is the seam broken before it is
  built.
* **One call, both collections.** `dal-002` requires a batch of ten with
  three invalid to leave seven observations and three quarantine rows. Split
  across two methods there is a window in which the observations are stored
  and their quarantine rows are not, and a run that fails in that window
  reports a clean ingest over a batch that lost three records.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.dal.models import CanonicalObservation


class QuarantineRecord(BaseModel):
    """A record that did not become an observation, and why.

    Attribution is best-effort: a record can fail *because* it is missing the
    field that identifies it, so `source_id` and `source_type` are optional
    and unparsed. `scenario_run_id` never is -- it comes from the ingest
    context rather than from the record, so the run is always known even when
    nothing else is.

    The raw source row is deliberately **not** kept. It would be useful for
    debugging, but a quarantined OpenSky row still carries a real `icao24`,
    and storing one would put in the database exactly the identifier
    `dal-004` exists to keep out of it. The failing field and the reason are
    enough to act on; the row itself stays in the local extract.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str | None
    source_type: str | None
    scenario_run_id: int
    observation_type: str | None
    field: str
    reason: str


class ObservationRepository(Protocol):
    """Where accepted and rejected records go."""

    def save_batch(
        self,
        observations: Sequence[CanonicalObservation],
        quarantined: Sequence[QuarantineRecord],
    ) -> None:
        """Persist both collections as one unit of work, or neither."""
        ...
