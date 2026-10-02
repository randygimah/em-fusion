"""PostGIS implementation of the DAL's repository port. Spec: db-003.

This file tests two different things, and the split matters.

**Most of it is behaviour against a live database**, marked and skipped when
`TEST_DATABASE_URL` is unset. A repository that has never written a row is an
untested repository, and asserting over a fake would only re-prove `dal-002`.

**A handful of it is structural, and asserts an absence** -- that the port's
signature did not change, that nothing under `app/dal/` imports a storage
engine, that no model carries a caller-supplied primary key. Those are the
`db-003` claim itself: the port was specified before any database existed, and
the item exists to find out whether it survived one. A test that watches for a
change cannot fail on the day it is written, so each is mutation-tested
separately rather than trusted; results are recorded in the test's own
docstring with the date.

The atomicity tests induce failure with a **real foreign-key violation** rather
than a patched method. `save_batch` writing two tables in one transaction is a
property of the database, and a repository that opened two transactions would
still pass against a mock that raised on the second call.
"""

from __future__ import annotations

import ast
import tomllib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.dal.ingest import ingest_batch
from app.dal.models import (
    CanonicalObservation,
    DataMode,
    Location,
    ObservationType,
    Provenance,
    SourceType,
    TrackPayload,
    ValidationStatus,
)
from app.dal.pseudonymise import Pseudonymiser
from app.dal.repository import ObservationRepository, QuarantineRecord
from app.dal.validation import IngestContext
from app.db.migrations import alembic_config
from app.db.repository import (
    PostgisObservationRepository,
    complete_scenario_run,
    detection_pass_for_run,
    record_detection_pass,
)
from tests.conftest import requires_database

BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: The run every fixture record belongs to. Both tables carry a NOT NULL foreign
#: key to `scenario_runs`, so a row cannot be written until one exists.
RUN_ID = 1

#: A run id that is deliberately absent from `scenario_runs`. Writing a record
#: against it violates the foreign key, which is how the atomicity tests induce
#: a real database failure rather than a simulated one.
MISSING_RUN_ID = 9999

#: Cologne, from row 0 of the extract. Kept distinct in both coordinates and in
#: sign-free magnitude so a latitude/longitude transposition cannot pass.
LAT = 51.0905
LON = 7.5473

#: Never the corpus seed. `dal-004` forbids committing that value, and a test
#: that needed it would be a test that could not run on a fresh clone.
PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")


# ------------------------------------------------------------------- builders


def _observation(
    *,
    run_id: int = RUN_ID,
    lat: float = LAT,
    lon: float = LON,
    aircraft_id: str = "AC-48089ab4e5a9",
) -> CanonicalObservation:
    return CanonicalObservation(
        source_id="opensky-replay",
        source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK,
        timestamp=datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC),
        location=Location(lat=lat, lon=lon),
        data_mode=DataMode.REPLAYED,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="opensky-replay",
            source_type=SourceType.OPENSKY,
            data_mode=DataMode.REPLAYED,
            scenario_run_id=run_id,
        ),
        payload=TrackPayload(
            aircraft_id=aircraft_id,
            flight_id="FL-0c53755a34bc",
            altitude_m=5753.1,
            velocity_ms=194.26,
            heading_deg=135.64,
            vertical_rate_ms=13.33,
            on_ground=False,
            position_staleness_s=1.06,
            contact_staleness_s=0.0,
        ),
    )


def _quarantine(*, run_id: int = RUN_ID, field: str = "location") -> QuarantineRecord:
    return QuarantineRecord(
        source_id="opensky-replay",
        source_type="opensky",
        scenario_run_id=run_id,
        observation_type="track",
        field=field,
        reason="field required",
    )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        )


# ------------------------------------------------------------------- fixtures


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    """An empty schema brought to head, holding one scenario run.

    The run exists because both tables carry a NOT NULL foreign key to it. It
    is inserted here rather than by the repository: creating a run is the
    scenario generator's job, and a repository that quietly created its own
    parent row would hide exactly the constraint the atomicity tests rely on.
    """
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", empty_database.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")

    with empty_database.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at) "
                "VALUES (:id, 'normal-baseline', '{}'::jsonb, 42, now())"
            ),
            {"id": RUN_ID},
        )
        connection.commit()
    return empty_database


@pytest.fixture
def repository(migrated_database: Engine) -> PostgisObservationRepository:
    return PostgisObservationRepository(
        sessionmaker(bind=migrated_database, autoflush=False)
    )


# ------------------------------------------------------- writing, live database


@pytest.mark.database
@requires_database
def test_save_batch_persists_an_observation(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    # spec: db-003
    repository.save_batch([_observation()], [])

    assert _count(migrated_database, "observations") == 1


@pytest.mark.database
@requires_database
def test_save_batch_persists_a_quarantine_record(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    # spec: db-003
    repository.save_batch([], [_quarantine()])

    assert _count(migrated_database, "quarantined_records") == 1


@pytest.mark.database
@requires_database
def test_ten_records_three_invalid_leave_seven_and_three(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """`dal-002`'s headline case, now against the real store.

    Proven once already against the in-memory fake. Repeated here because the
    claim it makes is about the storage layer's arithmetic, not the DAL's, and
    the fake cannot fail the way a database can.
    """
    # spec: db-003
    observations = [_observation(aircraft_id=f"AC-{index}") for index in range(7)]
    quarantined = [_quarantine(field=f"field-{index}") for index in range(3)]

    repository.save_batch(observations, quarantined)

    assert _count(migrated_database, "observations") == 7
    assert _count(migrated_database, "quarantined_records") == 3


@pytest.mark.database
@requires_database
def test_an_empty_batch_writes_nothing_and_does_not_raise(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """A window containing no rows is ordinary, not exceptional.

    `adp-001` yields per window, and a quiet window is a normal outcome rather
    than an error -- so the repository has to accept one without a special case
    at the call site.
    """
    # spec: db-003
    repository.save_batch([], [])

    assert _count(migrated_database, "observations") == 0
    assert _count(migrated_database, "quarantined_records") == 0


# ----------------------------------------------------------------- atomicity


@pytest.mark.database
@requires_database
def test_a_failing_quarantine_write_leaves_no_observations(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """The observations are valid; the quarantine record is not.

    Failure is induced by a real foreign-key violation rather than a patched
    method, because the property under test belongs to the database. A
    repository that committed the observations and then opened a second
    transaction for the quarantine records would satisfy a mock and fail here.
    """
    # spec: db-003
    with pytest.raises(IntegrityError):
        repository.save_batch([_observation()], [_quarantine(run_id=MISSING_RUN_ID)])

    assert _count(migrated_database, "observations") == 0
    assert _count(migrated_database, "quarantined_records") == 0


@pytest.mark.database
@requires_database
def test_a_failing_observation_write_leaves_no_quarantine_records(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """The mirror of the test above, and not redundant with it.

    Whichever collection the implementation happens to write first, a failure
    in the other must roll it back. One direction alone passes for a repository
    that is atomic by accident of ordering.
    """
    # spec: db-003
    with pytest.raises(IntegrityError):
        repository.save_batch([_observation(run_id=MISSING_RUN_ID)], [_quarantine()])

    assert _count(migrated_database, "observations") == 0
    assert _count(migrated_database, "quarantined_records") == 0


# ------------------------------------------------------------------- geometry


@pytest.mark.database
@requires_database
def test_location_is_stored_at_the_coordinates_it_was_given(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """Longitude is X and latitude is Y, and getting that backwards is silent.

    `ST_X` and `ST_Y` are asserted rather than a round-trip through the model,
    because a transposition that is symmetrical on the way in and out would
    round-trip perfectly while putting every aircraft in the wrong hemisphere.
    """
    # spec: db-003
    repository.save_batch([_observation()], [])

    with migrated_database.connect() as connection:
        x, y = connection.execute(
            text("SELECT ST_X(location), ST_Y(location) FROM observations")
        ).one()

    assert x == pytest.approx(LON)
    assert y == pytest.approx(LAT)


@pytest.mark.database
@requires_database
def test_location_is_stored_with_srid_4326(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """An unset SRID is 0, and `ST_DWithin` over SRID 0 answers in degrees.

    `db-004` casts this column to geography for its distance, and that cast
    silently means something else if the SRID is absent -- a 20 km radius
    becomes a 20 degree one, which is roughly the width of the corpus box.
    """
    # spec: db-003
    repository.save_batch([_observation()], [])

    with migrated_database.connect() as connection:
        srid = connection.execute(
            text("SELECT ST_SRID(location) FROM observations")
        ).scalar_one()

    assert srid == 4326


# ------------------------------------------------------------------ round trip


@pytest.mark.database
@requires_database
def test_provenance_is_written_to_its_own_columns(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """`dal-003`'s guarantee, at the far end of the pipeline.

    Provenance is asserted as columns rather than as part of the payload
    because it is queried -- "everything from this run" has to be an index
    scan, not a JSON traversal.
    """
    # spec: db-003
    repository.save_batch([_observation()], [])

    with migrated_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT source_id, source_type, data_mode, scenario_run_id, "
                "validation_status, observation_type FROM observations"
            )
        ).one()

    assert row.source_id == "opensky-replay"
    assert row.source_type == "opensky"
    assert row.data_mode == "replayed"
    assert row.scenario_run_id == RUN_ID
    assert row.validation_status == "valid"
    assert row.observation_type == "track"


@pytest.mark.database
@requires_database
def test_the_payload_round_trips_with_both_staleness_fields(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """The two clocks have to survive storage as two numbers.

    They are the discriminator between a coverage gap and a degraded position
    (`docs/thesis_notes.md`, the `contact_staleness_s` entry), so a payload
    that stores one and infers the other would collapse two scenario types
    into one at the point of writing.
    """
    # spec: db-003
    repository.save_batch([_observation()], [])

    with migrated_database.connect() as connection:
        payload = connection.execute(
            text("SELECT payload FROM observations")
        ).scalar_one()

    assert payload["aircraft_id"] == "AC-48089ab4e5a9"
    assert payload["position_staleness_s"] == pytest.approx(1.06)
    assert payload["contact_staleness_s"] == pytest.approx(0.0)


@pytest.mark.database
@requires_database
def test_the_quarantine_row_keeps_the_field_and_reason_and_no_raw_row(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """What a quarantine row is for, and what it must not carry.

    The failing field and the reason are what make the row actionable. The
    source row is absent by schema design: a quarantined OpenSky row still
    holds a real `icao24`, which is the identifier `dal-004` exists to keep
    out of the database.
    """
    # spec: db-003
    repository.save_batch([], [_quarantine(field="location")])

    with migrated_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT field, reason, source_id, source_type, "
                "observation_type, scenario_run_id FROM quarantined_records"
            )
        ).one()

    assert row.field == "location"
    assert row.reason == "field required"
    assert row.scenario_run_id == RUN_ID


# ------------------------------------------------------- the DAL through to PostGIS


@pytest.mark.database
@requires_database
def test_ingest_batch_persists_through_the_real_repository(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """The seam, exercised end to end for the first time.

    `ingest_batch` has only ever been run against the in-memory fake. Passing
    it the PostGIS implementation instead is what proves the port is a port
    rather than a shape the fake happens to fit.
    """
    # spec: db-003
    records = [
        {
            "source_id": "opensky-replay",
            "source_type": SourceType.OPENSKY,
            "observation_type": ObservationType.TRACK,
            "timestamp": datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC),
            "location": {"lat": LAT, "lon": LON},
            "payload": {
                "icao24": "3c6444",
                "callsign": "DLH8AT  ",
                "altitude_m": 5753.1,
                "velocity_ms": 194.26,
                "heading_deg": 135.64,
                "vertical_rate_ms": 13.33,
                "on_ground": False,
                "position_staleness_s": 1.06,
                "contact_staleness_s": 0.0,
            },
        },
        {
            "source_id": "opensky-replay",
            "source_type": SourceType.OPENSKY,
            "observation_type": ObservationType.TRACK,
            "timestamp": datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC),
            "location": {"lat": None, "lon": LON},
            "payload": {
                "icao24": "3c6445",
                "callsign": "DLH8AU  ",
                "on_ground": False,
                "position_staleness_s": 1.06,
                "contact_staleness_s": 0.0,
            },
        },
    ]

    result = ingest_batch(
        records,
        IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=RUN_ID),
        repository,
        PSEUDONYMISER,
    )

    assert result.accepted == 1
    assert result.quarantined == 1
    assert _count(migrated_database, "observations") == 1
    assert _count(migrated_database, "quarantined_records") == 1


@pytest.mark.database
@requires_database
def test_no_real_aircraft_identifier_reaches_the_database(
    repository: PostgisObservationRepository, migrated_database: Engine
) -> None:
    """`dal-004` holding at the far end of the pipeline rather than at the DAL.

    The adapter emits a real `icao24` on purpose -- the DAL can only substitute
    an identifier that reaches it -- so the only place to prove the substitution
    actually took is where the row lands. The stored payload is searched as raw
    text, because a leaked value under an unexpected key would pass a check that
    only looked at `aircraft_id`.
    """
    # spec: db-003
    ingest_batch(
        [
            {
                "source_id": "opensky-replay",
                "source_type": SourceType.OPENSKY,
                "observation_type": ObservationType.TRACK,
                "timestamp": datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC),
                "location": {"lat": LAT, "lon": LON},
                "payload": {
                    "icao24": "3c6444",
                    "callsign": "DLH8AT  ",
                    "on_ground": False,
                    "position_staleness_s": 1.06,
                    "contact_staleness_s": 0.0,
                },
            }
        ],
        IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=RUN_ID),
        repository,
        PSEUDONYMISER,
    )

    with migrated_database.connect() as connection:
        stored = connection.execute(
            text("SELECT payload::text FROM observations")
        ).scalar_one()

    assert "3c6444" not in stored
    assert "DLH8AT" not in stored
    assert "icao24" not in stored
    assert "callsign" not in stored


# ------------------------------------------------- the port, structurally

# The four tests below assert an *absence* and therefore pass on the day they
# are written. They are the `db-003` claim made mechanical -- the port was
# specified before a database existed, and these fail the moment it is widened
# to accommodate one. Each is mutation-tested rather than trusted; see the
# note in each docstring.


def test_the_port_signature_did_not_change_to_fit_postgis() -> None:
    """No storage-engine type crossed the port, and none was added.

    This is the standing prediction, written as an assertion: geometry and
    atomicity were judged the risks and identity not, and the way any of the
    three would show up is here, as a parameter the DAL has to know about.

    Mutation-tested 2026-09-02: widening `observations` to `Sequence[object]`
    turns this red. Note that *adding* a parameter does not -- that is the
    sibling test below, and the pair is deliberate: one watches the types that
    cross, the other watches how many.
    """
    # spec: db-003
    signature = get_type_hints(ObservationRepository.save_batch)

    assert signature["observations"] == Sequence[CanonicalObservation]
    assert signature["quarantined"] == Sequence[QuarantineRecord]
    assert signature["return"] is type(None)


def test_the_port_takes_exactly_two_collections_and_nothing_else() -> None:
    """One call, both collections -- the shape `dal-002` requires.

    Split across two methods there is a window in which the observations are
    stored and their quarantine rows are not, and a run failing in that window
    reports a clean ingest over a batch that lost records.

    Mutation-tested 2026-09-02: adding a third parameter to the Protocol
    turns this red.
    """
    # spec: db-003
    import inspect as _inspect

    parameters = list(_inspect.signature(ObservationRepository.save_batch).parameters)

    assert parameters == ["self", "observations", "quarantined"]


def test_the_dal_imports_no_storage_engine() -> None:
    """The seam, asserted at the import graph rather than by review.

    If anything under `app/dal/` imports SQLAlchemy, GeoAlchemy2, psycopg or
    `app.db`, the DAL knows about PostGIS and the port has stopped being one.

    Parsed rather than grepped: a substring match over the source is satisfied
    by an example inside a docstring, which is how the equivalent check in
    `dal-004` passed vacuously once already (`docs/qa.md` section 38).

    Mutation-tested 2026-09-02, both ways: adding `import sqlalchemy` to
    `app/dal/models.py` turns this red, and writing the same line inside that
    module's docstring leaves it green. The second half is the one worth
    running -- it is what distinguishes this from the grep it replaced.
    """
    # spec: db-003
    forbidden = ("sqlalchemy", "geoalchemy2", "psycopg", "app.db")
    offences: list[str] = []

    for path in sorted((BACKEND_ROOT / "app" / "dal").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module.split(".")[0] in forbidden or module in forbidden:
                    offences.append(f"{path.name}: {module}")

    assert offences == []


@pytest.mark.parametrize("model", [CanonicalObservation, QuarantineRecord])
def test_no_model_crossing_the_port_carries_a_primary_key(
    model: type,
) -> None:
    """The caller never supplies an identifier the database owns.

    A caller-supplied key is the quietest way a storage concern crosses the
    port: it looks like an ordinary field and makes the DAL responsible for
    uniqueness in a table it cannot see.

    Mutation-tested 2026-09-02: adding `id: int` to `QuarantineRecord` turns
    that parametrisation red and leaves the other green, which is also a check
    that the parametrisation is not collapsing both models into one assertion.
    """
    # spec: db-003
    assert not {"id", "pk", "observation_id"} & set(model.model_fields)


# ------------------------------------------------------------------- tooling


def test_the_geometry_warning_filter_is_gone() -> None:
    """`db-001` suppressed SQLAlchemy's unknown-`geometry` warning as a stopgap.

    The filter was added because GeoAlchemy2 was deliberately not a dependency
    yet. `db-003` adds it, so the suppression has to come out in the same
    change -- a warning filter left in place hides the *next* unrecognised
    type as well as the one it was written for.
    """
    # spec: db-003
    config = tomllib.loads(
        (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    filters = config["tool"]["pytest"]["ini_options"].get("filterwarnings", [])

    assert not [entry for entry in filters if "geometry" in entry]


def test_geoalchemy2_is_a_declared_dependency() -> None:
    """Declared in `pyproject.toml`, not merely importable in the venv.

    An undeclared import works on the machine that installed it by hand and
    fails in the container, which is the failure mode the committed lockfile
    exists to prevent.
    """
    # spec: db-003
    config = tomllib.loads(
        (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert "geoalchemy2" in [name.lower() for name in config["project"]["dependencies"]]


# ------------------------------------------------------------- run completion


def _completed_at(engine: Engine, run_id: int) -> object:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT completed_at FROM scenario_runs WHERE id = :id"),
            {"id": run_id},
        ).scalar_one()


def _insert_second_run(engine: Engine, run_id: int) -> None:
    with engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at) "
                "VALUES (:id, 'normal-baseline', '{}'::jsonb, 43, now())"
            ),
            {"id": run_id},
        )
        connection.commit()


@pytest.mark.database
@requires_database
def test_a_newly_created_run_is_not_marked_complete(
    migrated_database: Engine,
) -> None:
    # spec: db-007 -- the column's meaning stated as an assertion: a run is not
    # known to have finished until something says so. A server default added
    # later would turn this red, which is the point of asserting it separately
    # from the marking test below.
    assert _completed_at(migrated_database, RUN_ID) is None


@pytest.mark.database
@requires_database
def test_completing_a_run_marks_it(migrated_database: Engine) -> None:
    # spec: db-007
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    complete_scenario_run(factory, RUN_ID)

    assert _completed_at(migrated_database, RUN_ID) is not None


@pytest.mark.database
@requires_database
def test_completing_one_run_does_not_complete_another(
    migrated_database: Engine,
) -> None:
    """The WHERE clause, asserted rather than read.

    An `UPDATE scenario_runs SET completed_at = now()` with no predicate marks
    every run in the database complete and passes every other test in this
    section, because the fixture holds exactly one run. The second run is what
    makes the omission visible.
    """
    # spec: db-007
    other_run = RUN_ID + 1
    _insert_second_run(migrated_database, other_run)
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    complete_scenario_run(factory, RUN_ID)

    assert _completed_at(migrated_database, RUN_ID) is not None
    assert _completed_at(migrated_database, other_run) is None


@pytest.mark.database
@requires_database
def test_completing_a_run_that_does_not_exist_raises(
    migrated_database: Engine,
) -> None:
    """An UPDATE matching no rows is a success by default, and must not be.

    PostgreSQL reports no error for an `UPDATE ... WHERE id = 9999` against a
    table with no such row; it reports zero rows affected. Left unchecked, a
    caller holding the wrong run id would mark nothing and be told it worked,
    which is the silent completion this column exists to make impossible.
    """
    # spec: db-007
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    with pytest.raises(LookupError):
        complete_scenario_run(factory, MISSING_RUN_ID)

    assert _completed_at(migrated_database, RUN_ID) is None


# Mutation result, 2026-09-04: deleting `WHERE id = :run_id` from
# `complete_scenario_run` turned `..._does_not_complete_another` and
# `..._that_does_not_exist_raises` red, and left the other two green -- which is
# the point of holding a second run in the first of those. An UPDATE with no
# predicate marks every run in the database complete and satisfies a test that
# only ever looks at the run it asked for.


# --------------------------------------------------------- the detection stamp
#
# Spec: anom-015 (second amendment), api-012. Parallel to `db-007`'s completion
# stamp and nullable for its reason: absence means *not known to have been
# scored*, which is the only state the findings table cannot express -- the
# write replaces per run per rule including at zero, so a run examined and found
# clean leaves exactly what a run nobody examined leaves.


POLICY = {"RF-NOISE.threshold_db": "6.0", "BASELINE.quiet_run_count": "60"}


@pytest.mark.database
@requires_database
def test_a_run_never_scored_reports_no_detection_pass(
    migrated_database: Engine,
) -> None:
    # spec: anom-015, api-012 -- null is the informative state, as db-007's
    # completion stamp is. Nothing has examined this run.
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    assert detection_pass_for_run(factory, RUN_ID) is None


@pytest.mark.database
@requires_database
def test_recording_a_detection_pass_stamps_the_run(migrated_database: Engine) -> None:
    """Spec: anom-015, api-012, eval-003.

    The policy travels with the stamp because a quiet run has no findings to
    carry it. The time is the **database's** clock and not the caller's,
    following `complete_scenario_run` one function up: when something happened
    to a run is one clock's to keep, or two producers on two machines write
    times that cannot be ordered against each other.
    """
    # spec: anom-015, api-012, eval-003, db-007
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    record_detection_pass(factory, RUN_ID, policy=POLICY)
    recorded = detection_pass_for_run(factory, RUN_ID)

    assert recorded is not None
    assert recorded.scenario_run_id == RUN_ID
    assert recorded.at.tzinfo is not None
    assert recorded.policy == POLICY


@pytest.mark.database
@requires_database
def test_recording_one_pass_does_not_stamp_another_run(
    migrated_database: Engine,
) -> None:
    """The WHERE clause, asserted rather than read.

    `db-007`'s own test records why: an UPDATE with no predicate marks every run
    in the database and passes every other test here, the fixture holding one
    run. Worse on this column than on that one -- a stamp claims a run was
    examined, so a missing predicate reports the whole corpus as scored.
    """
    # spec: anom-015, db-007
    other_run = RUN_ID + 1
    _insert_second_run(migrated_database, other_run)
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    record_detection_pass(factory, RUN_ID, policy=POLICY)

    assert detection_pass_for_run(factory, RUN_ID) is not None
    assert detection_pass_for_run(factory, other_run) is None


@pytest.mark.database
@requires_database
def test_stamping_a_run_that_does_not_exist_is_refused(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015, db-002.

    `db-002`'s grounding write established the rule: an UPDATE matching nothing
    succeeds at the database while losing the fact here. A pass that silently
    recorded nothing would leave the run reporting itself unexamined after a
    complete examination, which is the one direction that cannot be noticed --
    the endpoint simply serves no summary, exactly as it would before any pass.
    """
    # spec: anom-015, db-002
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    with pytest.raises(LookupError, match=str(MISSING_RUN_ID)):
        record_detection_pass(factory, MISSING_RUN_ID, policy=POLICY)


@pytest.mark.database
@requires_database
def test_a_second_pass_replaces_the_first_rather_than_appending(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015, db-008.

    The findings write replaces per run per rule, so a re-scored run holds one
    set of findings. A stamp that accumulated would leave the run claiming two
    examinations under two policies while the rows came from one of them.
    """
    # spec: anom-015, db-008
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    record_detection_pass(factory, RUN_ID, policy=POLICY)
    first = detection_pass_for_run(factory, RUN_ID)
    record_detection_pass(
        factory, RUN_ID, policy={**POLICY, "RF-NOISE.threshold_db": "8.0"}
    )

    recorded = detection_pass_for_run(factory, RUN_ID)
    assert first is not None and recorded is not None
    assert recorded.at >= first.at
    assert recorded.policy["RF-NOISE.threshold_db"] == "8.0"
