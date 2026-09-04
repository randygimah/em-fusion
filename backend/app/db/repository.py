"""PostGIS implementation of the DAL's repository port. Spec: db-003.

The second implementation of `ObservationRepository`, alongside the in-memory
fake in `tests/fakes.py`. Both are held to the same Protocol, which is what
makes it a port rather than a shape one caller happens to fit; the fake is
kept rather than replaced, so the unit tier still runs with no Docker.

**The Protocol's signature is unchanged**, which was the open question this
item existed to answer. `save_batch` still takes two sequences of Pydantic
models and returns `None`. The conversions a database needs -- coordinates to
a geometry, enum members to their values, models to JSON -- all happen below
this line. `db-005` said the session dependency closes but does not commit
precisely so that this module could own the transaction, and it does.

**The schema is reflected, not redeclared.** `db-001`'s migration is the
single source of truth for the table shape, and a second declaration here
would be a copy that drifts silently -- a renamed column would fail at write
time with a message about the copy rather than about the schema. Reflection is
also where GeoAlchemy2 earns its place: without it SQLAlchemy cannot read a
`geometry` column back and warns once per column, which is exactly the warning
`db-001` had to suppress and this item removed.

**Geometry is built as EWKT rather than by casting in SQL.** `WKTElement`
carries its SRID with it, so a point cannot be inserted with the SRID
unset -- and an unset SRID is 0, over which `db-004`'s `ST_DWithin` would
silently answer in degrees rather than metres.

EWKT (Extended Well-Known Text) is a text format for describing map shapes and
location data. It is a superset of WKT (Well-Known Text) that carries additional
information, notably the spatial reference system identifier (SRID). Geometries
are written in a human-readable form, which makes spatial data easier to read
and work with.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from geoalchemy2 import WKTElement
from sqlalchemy import MetaData, Table, insert, text
from sqlalchemy.orm import Session, sessionmaker

from app.dal.models import CanonicalObservation
from app.dal.repository import QuarantineRecord

OBSERVATIONS = "observations"
QUARANTINED_RECORDS = "quarantined_records"

#: WGS 84, the SRID every geometry column in `db-001` declares.
SRID = 4326


def _point(lon: float, lat: float) -> WKTElement:
    """A point in EWKT, longitude first.

    Longitude is X and latitude is Y, and the two are the same kind of number,
    so a transposition here produces valid geometry in the wrong hemisphere and
    no error anywhere. Written as one function so there is exactly one place
    the order is decided.
    """
    return WKTElement(f"POINT({lon} {lat})", srid=SRID)


class PostgisObservationRepository:
    """Writes canonical observations and quarantine records to PostgreSQL."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._metadata: MetaData | None = None

    def save_batch(
        self,
        observations: Sequence[CanonicalObservation],
        quarantined: Sequence[QuarantineRecord],
    ) -> None:
        """Persist both collections as one unit of work, or neither.

        `sessionmaker.begin()` commits on a clean exit and rolls back on any
        exception, so the two inserts share one transaction. That is the whole
        of `dal-002`'s guarantee at this layer: a batch of ten with three
        invalid leaves seven observations and three quarantine rows, and a
        failure between the two writes leaves none of either.
        """
        with self._session_factory.begin() as session:
            observations_table, quarantined_table = self._tables(session)

            if observations:
                session.execute(
                    insert(observations_table),
                    [_observation_row(item) for item in observations],
                )
            if quarantined:
                session.execute(
                    insert(quarantined_table),
                    [_quarantine_row(item) for item in quarantined],
                )

    def _tables(self, session: Session) -> tuple[Table, Table]:
        """The two tables, reflected once per repository and then reused.

        Reflected inside the caller's transaction rather than in `__init__`,
        because construction must not require a reachable database -- the same
        property `db-005` protects for the Engine, for the same reason.
        """
        if self._metadata is None:
            metadata = MetaData()
            metadata.reflect(
                bind=session.connection(),
                only=(OBSERVATIONS, QUARANTINED_RECORDS),
            )
            self._metadata = metadata
        return (
            self._metadata.tables[OBSERVATIONS],
            self._metadata.tables[QUARANTINED_RECORDS],
        )


def _observation_row(observation: CanonicalObservation) -> dict[str, Any]:
    """One canonical observation as a row.

    Enum members are unwrapped with `.value` rather than passed through. They
    subclass `str`, so passing one is silently accepted and can render as
    `SourceType.OPENSKY` -- the Python identifier in place of the source's own
    name for itself. `app/dal/ingest.py` documents the same trap one field over.

    Provenance is written twice on purpose: as four columns, because "every
    observation from this run" has to be an index scan rather than a JSON
    traversal, and as JSONB, because `dal-003` requires the attached record to
    survive intact rather than as four fields that happen to agree with it.
    """
    return {
        "source_id": observation.source_id,
        "source_type": observation.source_type.value,
        "observation_type": observation.observation_type.value,
        "timestamp": observation.timestamp,
        "location": _point(observation.location.lon, observation.location.lat),
        "data_mode": observation.data_mode.value,
        "validation_status": observation.validation_status.value,
        "scenario_run_id": observation.provenance.scenario_run_id,
        "provenance": observation.provenance.model_dump(mode="json"),
        "payload": observation.payload.model_dump(mode="json"),
    }


def _quarantine_row(record: QuarantineRecord) -> dict[str, Any]:
    """One quarantine record as a row.

    No raw source row, because the schema has no column for one: a quarantined
    OpenSky row still carries a real `icao24`, which is the identifier
    `dal-004` exists to keep out of the database. `created_at` is left to the
    server default -- when a record was quarantined is the database's clock to
    keep, not the caller's.
    """
    return {
        "source_id": record.source_id,
        "source_type": record.source_type,
        "observation_type": record.observation_type,
        "scenario_run_id": record.scenario_run_id,
        "field": record.field,
        "reason": record.reason,
    }


def complete_scenario_run(session_factory: sessionmaker[Session], run_id: int) -> None:
    """Mark a run as having finished. Spec: db-007.

    A free function rather than a method on the repository above, because
    every producer of a run has to set this and not every producer writes
    observations -- `scn-001`'s generator will create runs, and a run marked
    complete only by whoever happened to hold an observation repository would
    be a rule enforced by coincidence.

    The timestamp is `now()` rather than a value from the caller, for the same
    reason `quarantined_records.created_at` is a server default: when a run
    finished is the database's clock to keep, and two producers on two machines
    would otherwise write completion times that cannot be ordered against each
    other.

    Raises `LookupError` when the run does not exist. PostgreSQL reports no
    error for an `UPDATE` that matches nothing -- it reports zero rows
    affected -- so a caller holding the wrong id would otherwise mark nothing
    and be told it worked, which is the silent completion this column exists to
    make impossible.
    """
    with session_factory.begin() as session:
        # `session.connection()` rather than `session.execute()`, which is
        # typed as returning a `Result` and does not carry `rowcount` -- the
        # one thing this function needs from it. Same connection, same
        # transaction, as `_tables` above.
        result = session.connection().execute(
            text("UPDATE scenario_runs SET completed_at = now() WHERE id = :run_id"),
            {"run_id": run_id},
        )
        if result.rowcount != 1:
            raise LookupError(
                f"scenario run {run_id} does not exist, so it cannot be marked "
                f"complete: {result.rowcount} rows updated."
            )
