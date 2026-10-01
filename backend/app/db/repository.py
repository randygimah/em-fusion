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

import json
from collections.abc import Mapping, Sequence
from typing import Any

from geoalchemy2 import WKTElement
from sqlalchemy import MetaData, RowMapping, Table, insert, text
from sqlalchemy.orm import Session, sessionmaker

from app.dal.models import (
    PAYLOAD_TYPES,
    CanonicalObservation,
    Location,
    ObservationType,
    Provenance,
    ScenarioRunDetail,
    ScenarioRunSummary,
)
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


def create_scenario_run(
    session_factory: sessionmaker[Session],
    *,
    scenario_type: str,
    parameters: Mapping[str, Any],
    seed: int,
    ground_truth: Mapping[str, Any] | None = None,
) -> int:
    """Open a run and return its id. Spec: scn-001.

    A free function beside `complete_scenario_run` and for the same reason:
    every producer of a run creates one, and not every producer writes
    observations. It lives here rather than in the command that happens to call
    it -- `app/replay.py` held this SQL from `adp-007` until `scn-001` arrived
    to claim it -- because the repository is the only place SQL may go, and a
    second `INSERT` written by the next producer would be a second definition
    of what a run is.

    **The seed is written, always.** It is the argument rather than a default,
    so a caller cannot open a run without deciding one, and `RunSpec.create`
    draws it before this is ever reached. A run whose seed was never recorded
    cannot be repeated, which is `scn-001`'s third failure case.

    `started_at` is `now()` -- the database's clock, as with `completed_at` --
    and `ground_truth` is left null: what a run staged is `scn-002`'s to write,
    and `api-009` requires it never to leave the run record in any case.

    Parameters are serialised here rather than bound as a dictionary, because a
    `text()` statement carries no type information for psycopg to adapt
    against. Sorted keys so that two runs configured identically produce
    identical rows.

    `ground_truth` is what the run intends to stage, written with the row so
    that a run which dies part-way still says what it was attempting
    (`scn-002`). It stays null when there is nothing staged to describe -- a
    replay has no answer key, and null says so, whereas an empty object would
    claim the run staged nothing, which only the quiet control is entitled to
    say.
    """
    with session_factory.begin() as session:
        return int(
            session.execute(
                text(
                    "INSERT INTO scenario_runs "
                    "(scenario_type, parameters, seed, started_at, ground_truth) "
                    "VALUES (:scenario_type, CAST(:parameters AS jsonb), "
                    ":seed, now(), CAST(:ground_truth AS jsonb)) RETURNING id"
                ),
                {
                    "scenario_type": scenario_type,
                    "parameters": json.dumps(dict(parameters), sort_keys=True),
                    "seed": seed,
                    "ground_truth": (
                        None
                        if ground_truth is None
                        else json.dumps(dict(ground_truth), sort_keys=True)
                    ),
                },
            ).scalar_one()
        )


def record_ground_truth(
    session_factory: sessionmaker[Session], run_id: int, truth: Mapping[str, Any]
) -> None:
    """Write the finished answer key onto a run. Spec: scn-002.

    The second instalment. What a run *planned* to stage is known before it
    starts and is written with the row; which aircraft it actually touched is
    known only once the corpus has streamed past, because whether a targeted
    aircraft appears inside the zone during the window is a property of the
    data rather than of the seed. An answer key naming aircraft that never
    appeared would score the detector as missing things it was never shown.

    Both instalments happen at generation time. Nothing here is ever derived
    from detector output, which is the line that makes a measurement against
    this record mean anything.

    Raises `LookupError` on an unknown run, for the reason `db-007` gives: an
    `UPDATE` matching nothing is a success by default, so a caller holding the
    wrong id would write the answer key nowhere and be told it worked -- and
    the run would then be scored against an absent ground truth.
    """
    with session_factory.begin() as session:
        result = session.connection().execute(
            text(
                "UPDATE scenario_runs SET ground_truth = CAST(:truth AS jsonb) "
                "WHERE id = :run_id"
            ),
            {"truth": json.dumps(dict(truth), sort_keys=True), "run_id": run_id},
        )
        if result.rowcount != 1:
            raise LookupError(
                f"scenario run {run_id} does not exist, so its ground truth "
                f"cannot be recorded: {result.rowcount} rows updated."
            )


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


def latest_run(session_factory: sessionmaker[Session]) -> ScenarioRunSummary | None:
    """The run to serve, or None when nothing has ever run. Spec: api-002.

    **A run known to have completed beats a more recent one that is not.** The
    obvious query -- most recent by start time -- would serve a replay that
    died half-way as though it were a whole hour, which is precisely the
    ambiguity `db-007` added `completed_at` to remove. Falling back to the most
    recent run when none has completed is deliberate: with nothing finished,
    serving an unfinished run is more useful than serving nothing, and the
    screen has no way to show data that was never written.

    Ground truth is not selected. `api-009` requires it never to leave the run
    record, and `ScenarioRunSummary` has no field to put it in.
    """
    with session_factory.begin() as session:
        row = (
            session.execute(
                text(
                    "SELECT id, scenario_type, seed, started_at, completed_at "
                    "FROM scenario_runs "
                    "ORDER BY (completed_at IS NOT NULL) DESC, "
                    "started_at DESC, id DESC LIMIT 1"
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else ScenarioRunSummary(**row)


def list_runs(
    session_factory: sessionmaker[Session], limit: int = 50
) -> list[ScenarioRunDetail]:
    """Recent runs, newest first, for the Scenario Control screen. Spec: api-006.

    Ordered by start time rather than by completion, because this table is a
    record of what was asked for -- a run that died is still a run somebody
    started, and `db-007` makes its null completion stamp the thing that says
    so. `latest_run` orders differently on purpose: it is choosing one run to
    serve and prefers a finished one.

    **`ground_truth` is not selected.** `api-009` requires the answer key never
    to leave the run record, and `ScenarioRunDetail` has no field to put it in,
    so the column is absent from both the query and the shape.
    """
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    "SELECT id, scenario_type, seed, started_at, completed_at, "
                    "parameters FROM scenario_runs "
                    "ORDER BY started_at DESC, id DESC LIMIT :limit"
                ),
                {"limit": limit},
            )
            .mappings()
            .all()
        )
        return [ScenarioRunDetail(**row) for row in rows]


def latest_positions(
    session_factory: sessionmaker[Session], run_id: int, window_seconds: int
) -> list[CanonicalObservation]:
    """Where each aircraft was last seen, within the run's final window.

    Two reductions, both in SQL rather than in Python, because the alternative
    is reading 133,134 rows into the application to discard all but a few
    hundred of them.

    `DISTINCT ON` keeps one row per aircraft -- the newest, by the `ORDER BY`
    it requires -- which is the screen's question: where is each aircraft, not
    everywhere each aircraft has been. The window bounds that to aircraft seen
    near the end of the run: an aircraft last reported fifty minutes ago is not
    in the sector now, and drawing it as though it were is the map lying.

    The window is measured from the newest observation in the run rather than
    from the wall clock, because a replayed hour from 2022 has no relationship
    to the time now. Rows come back as `CanonicalObservation` -- the same model
    that went in -- so nothing above this line learns a storage type.
    """
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    "WITH final AS ("
                    "  SELECT max(timestamp) AS ends_at FROM observations "
                    "  WHERE scenario_run_id = :run_id"
                    ") "
                    "SELECT DISTINCT ON (payload->>'aircraft_id') "
                    "  source_id, source_type, observation_type, timestamp, "
                    "  data_mode, validation_status, provenance, payload, "
                    "  ST_Y(location) AS lat, ST_X(location) AS lon "
                    "FROM observations, final "
                    "WHERE scenario_run_id = :run_id "
                    "  AND timestamp > final.ends_at "
                    "      - make_interval(secs => :window_seconds) "
                    "ORDER BY payload->>'aircraft_id', timestamp DESC"
                ),
                {"run_id": run_id, "window_seconds": window_seconds},
            )
            .mappings()
            .all()
        )
    return [_observation(row) for row in rows]


def observations_for_run(
    session_factory: sessionmaker[Session],
    run_id: int,
    observation_type: ObservationType,
) -> list[CanonicalObservation]:
    """Every observation of one kind for one run, oldest first. Spec: anom-015.

    The read `anom-015` needs, and it belongs here rather than in the caller for
    `FR-904`'s reason: both measurement scripts grew their own, each holding raw
    SQL that **invents five fields** -- `source_id="o"`, a source type and data
    mode derived from the observation type rather than read, `VALID` asserted
    without checking, and a `Provenance` built from scratch. `_observation` below
    reconstructs all five from the row and picks the payload class by type. The
    hardcoded mapping happens to agree with what the generator writes, which makes
    it a right answer from a wrong source -- `ai-004`'s defect, and the one
    `anom-015` exists to stop repeating one layer up.

    Ordered by timestamp, which is not presentation: every rule downstream reads
    a series, `anom-001` walks episodes of consecutive readings, and an unordered
    result takes its order from the heap -- the failure this repository has
    recorded three times.

    No window and no reduction, unlike `latest_positions`: a detection pass reads
    the whole run by definition, and a pass over part of one is `anom-015`'s
    refusal rather than a smaller correct answer.
    """
    with session_factory() as session:
        rows = (
            session.execute(
                text(
                    "SELECT source_id, source_type, observation_type, timestamp, "
                    "       ST_Y(location) AS lat, ST_X(location) AS lon, "
                    "       data_mode, validation_status, provenance, payload "
                    "FROM observations "
                    "WHERE scenario_run_id = :run_id "
                    "  AND observation_type = :observation_type "
                    "ORDER BY timestamp, id"
                ),
                {"run_id": run_id, "observation_type": observation_type.value},
            )
            .mappings()
            .all()
        )
    return [_observation(row) for row in rows]


def _observation(row: RowMapping) -> CanonicalObservation:
    """One row back into the model it was written from.

    The payload class is chosen by observation type rather than left to the
    union to infer. `CanonicalObservation` rejects a track carrying an RF
    payload, and a union in smart mode resolves by shape -- so an inferred
    payload would be right until two payload types happened to share a shape,
    and wrong in a way that reads as a validation bug rather than a read bug.
    """
    observation_type = ObservationType(row["observation_type"])
    return CanonicalObservation(
        source_id=row["source_id"],
        source_type=row["source_type"],
        observation_type=observation_type,
        timestamp=row["timestamp"],
        location=Location(lat=row["lat"], lon=row["lon"]),
        data_mode=row["data_mode"],
        validation_status=row["validation_status"],
        provenance=Provenance(**row["provenance"]),
        payload=PAYLOAD_TYPES[observation_type].model_validate(row["payload"]),
    )
