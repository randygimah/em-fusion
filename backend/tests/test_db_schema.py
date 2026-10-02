"""Core schema and migrations. Spec: db-001.

Every test here needs a live PostgreSQL with PostGIS, and every one of them is
marked so it skips when `TEST_DATABASE_URL` is unset. That is what keeps
`db-005`'s guarantee intact -- the unit suite still runs on a machine with no
Docker -- while giving this item the only thing that can actually prove it. A
migration that has never been applied is an untested migration, and reading the
DDL is the same class of evidence as asserting a test passed without running it.

`TEST_DATABASE_URL` is deliberately a different variable from `DATABASE_URL`.
These tests drop and recreate schema; keying them on the application's own
connection string would eventually run a `DROP` against a database someone
cared about.
"""

from __future__ import annotations

import pytest
from alembic.config import Config
from sqlalchemy import DateTime, Engine, inspect, text

from alembic import command
from app.db.migrations import alembic_config
from tests.conftest import requires_database

pytestmark = [pytest.mark.database, requires_database]

#: Seven, not the six in the ERD as first drawn. `quarantined_records` was added
#: 2026-08-29: a QuarantineRecord carries no timestamp, location or payload,
#: because those are the fields that failed validation, so `observations` cannot
#: hold one without making those columns nullable -- which would delete the
#: NOT NULL guarantee `dal-003` defers to this item.
EXPECTED_TABLES = {
    "observations",
    "quarantined_records",
    "anomalies",
    "evidence_bundles",
    "hypotheses",
    "analyst_feedback",
    "scenario_runs",
}

#: `db-002` requires these on `hypotheses` from the *first* revision. They have
#: no consumer for several phases, which is exactly why they are asserted now:
#: `raw_response` is not retrofittable after an evaluation campaign has run.
REPRODUCIBILITY_COLUMNS = {
    "generator",
    "model_id",
    "generation_params",
    "raw_response",
}


def _config_for(engine: Engine) -> Config:
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False)
    )
    return config


def _upgrade(engine: Engine) -> None:
    command.upgrade(_config_for(engine), "head")


def _columns(engine: Engine, table: str) -> dict[str, object]:
    return {column["name"]: column for column in inspect(engine).get_columns(table)}


# ------------------------------------------------------------------ migrations


def test_migrations_apply_cleanly_from_empty(empty_database: Engine) -> None:
    # spec: db-001
    _upgrade(empty_database)

    assert EXPECTED_TABLES <= set(inspect(empty_database).get_table_names())


def test_migrations_applied_twice_from_empty_do_not_error(
    empty_database: Engine,
) -> None:
    # spec: db-001 -- the named failure case. The second run is a no-op because
    # alembic_version records what has already been applied; without that table
    # the second CREATE TABLE would raise.
    _upgrade(empty_database)
    _upgrade(empty_database)

    assert EXPECTED_TABLES <= set(inspect(empty_database).get_table_names())


def test_alembic_records_the_applied_revision(empty_database: Engine) -> None:
    # spec: db-001 -- the version table is the whole reason Alembic was chosen
    # over ordered SQL files, so its presence is asserted rather than assumed
    _upgrade(empty_database)

    with empty_database.connect() as connection:
        revisions = (
            connection.execute(text("SELECT version_num FROM alembic_version"))
            .scalars()
            .all()
        )

    assert len(revisions) == 1
    assert revisions[0]


def test_missing_postgis_extension_fails_at_migration_time(
    database_without_postgis: Engine,
) -> None:
    # spec: db-001 -- the failure this guards is a *late* one: without the
    # check, the schema builds, the service reports healthy, and the first
    # spatial query dies with `type "geography" does not exist` far from the
    # cause. The message must name the extension.
    with pytest.raises(RuntimeError, match="postgis"):
        _upgrade(database_without_postgis)


# ---------------------------------------------------------------- spatial columns


def test_observations_location_is_a_point_geometry_in_4326(
    empty_database: Engine,
) -> None:
    # spec: db-001, db-004
    _upgrade(empty_database)

    with empty_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT type, srid, coord_dimension FROM geometry_columns "
                "WHERE f_table_name = 'observations' AND f_geometry_column = 'location'"
            )
        ).one()

    assert row.type == "POINT"
    assert row.srid == 4326
    assert row.coord_dimension == 2


def test_anomalies_affected_area_is_a_polygon_geometry_in_4326(
    empty_database: Engine,
) -> None:
    # spec: db-001, db-004
    _upgrade(empty_database)

    with empty_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT type, srid FROM geometry_columns "
                "WHERE f_table_name = 'anomalies' "
                "AND f_geometry_column = 'affected_area'"
            )
        ).one()

    assert row.type == "POLYGON"
    assert row.srid == 4326


@pytest.mark.parametrize(
    ("table", "column"),
    [("observations", "location"), ("anomalies", "affected_area")],
)
def test_spatial_columns_are_gist_indexed(
    empty_database: Engine, table: str, column: str
) -> None:
    # spec: db-001, db-004 -- without the index the clustering query in db-004
    # still returns correct answers, by sequential scan. It fails as a
    # performance claim rather than a correctness one, which is the kind of
    # defect that survives every functional test.
    _upgrade(empty_database)

    with empty_database.connect() as connection:
        definitions = (
            connection.execute(
                text("SELECT indexdef FROM pg_indexes WHERE tablename = :table"),
                {"table": table},
            )
            .scalars()
            .all()
        )

    assert any(
        "USING gist" in definition and column in definition
        for definition in definitions
    ), f"no GiST index on {table}.{column}: {definitions}"


def test_db004s_query_shape_compiles_against_the_stored_columns(
    empty_database: Engine,
) -> None:
    # spec: db-001, db-004 -- the columns are stored as geometry and cast to
    # geography at query time, so this runs db-004's actual predicate shape
    # against the real columns rather than against literals. Over zero rows it
    # returns nothing, but PostgreSQL still resolves the cast and the function
    # signature, so a location that was text, or already geography, or absent,
    # fails here. An earlier version of this test computed a distance between
    # two literal points, which would have passed against a schema with no
    # geometry columns at all -- it proved PostGIS was installed, which another
    # test already covers, and nothing about this schema.
    _upgrade(empty_database)

    with empty_database.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT o.id FROM observations o JOIN anomalies a ON true "
                "WHERE ST_DWithin("
                "  o.location::geography, a.affected_area::geography, :radius_m)"
            ),
            {"radius_m": 5_000},
        ).all()

    assert rows == []


# -------------------------------------------------------------- column contracts


def test_observation_payload_is_jsonb(empty_database: Engine) -> None:
    # spec: db-001 -- source-specific fields live in the payload so the
    # canonical table stays stable as adapters are added. JSONB rather than
    # JSON, because only JSONB can be indexed and queried by key.
    _upgrade(empty_database)

    assert str(_columns(empty_database, "observations")["payload"]["type"]) == "JSONB"


def test_hypotheses_carries_the_reproducibility_columns(
    empty_database: Engine,
) -> None:
    # spec: db-001, db-002 -- from the first revision, not a later one. Nothing
    # writes to this table for several phases; the column that matters,
    # raw_response, cannot be added after a campaign has already run.
    _upgrade(empty_database)

    assert REPRODUCIBILITY_COLUMNS <= set(_columns(empty_database, "hypotheses"))


@pytest.mark.parametrize(
    "column", ["scenario_run_id", "data_mode", "source_id", "source_type"]
)
def test_observations_provenance_is_not_nullable(
    empty_database: Engine, column: str
) -> None:
    # spec: db-001, dal-003 -- the half dal-003 defers to here. The DAL refuses
    # to *construct* a record without provenance; the schema must refuse to
    # *store* one, and only one of those two is asserted by dal-003's own tests.
    _upgrade(empty_database)

    assert _columns(empty_database, "observations")[column]["nullable"] is False


@pytest.mark.parametrize("column", ["scenario_run_id", "field", "reason"])
def test_quarantine_attribution_is_not_nullable(
    empty_database: Engine, column: str
) -> None:
    # spec: db-001, dal-002 -- a quarantine row that cannot say which run it
    # belongs to, or why the record failed, records that something went wrong
    # without recording anything actionable
    _upgrade(empty_database)

    assert _columns(empty_database, "quarantined_records")[column]["nullable"] is False


@pytest.mark.parametrize("column", ["source_id", "source_type", "observation_type"])
def test_quarantine_attribution_is_best_effort(
    empty_database: Engine, column: str
) -> None:
    # spec: db-001, dal-002 -- these three are nullable *on purpose*: a record
    # can fail precisely because it is missing the field that identifies it, so
    # a NOT NULL here would make the unattributable record unstorable and force
    # the silent drop dal-002 forbids
    _upgrade(empty_database)

    assert _columns(empty_database, "quarantined_records")[column]["nullable"] is True


def test_quarantined_records_do_not_store_the_raw_source_row(
    empty_database: Engine,
) -> None:
    # spec: db-001, dal-004 -- a quarantined OpenSky row still carries a real
    # icao24. Storing it would put in the database the identifier dal-004 exists
    # to keep out, one query away from anyone with database access.
    _upgrade(empty_database)

    columns = set(_columns(empty_database, "quarantined_records"))

    assert not columns & {"raw", "raw_row", "source_row", "payload", "icao24"}


# Mutation results, 2026-08-29. These three assertions were each confirmed to
# fail when the property they claim is removed, because two of them assert an
# absence or a property PostgreSQL would not otherwise complain about:
#
#   * adding a `raw_row` column to `quarantined_records` turned the test above
#     red;
#   * deleting the `CREATE INDEX ... USING GIST` line turned both
#     `test_spatial_columns_are_gist_indexed` cases red;
#   * changing the columns from `geometry` to `geography` turned both
#     `..._is_a_point/polygon_geometry_in_4326` cases red, while
#     `test_db004s_query_shape_compiles_against_the_stored_columns` stayed
#     green -- correctly, since a `::geography` cast is valid on either, which
#     is why the column-type tests exist separately from the query-shape one.
#
# The GiST mutation is worth a note of its own: the first attempt at it edited
# a multi-line source string that Black had already collapsed onto one line, so
# the substitution silently matched nothing and the test "passed" against an
# unmutated file. A mutation test that did not mutate proves less than no test
# at all, because it reports confidence. Every mutation here now asserts that
# its own substitution applied before the suite is run.


# --------------------------------------------------------------- run completion

#: The revision `0002` builds on, and the target a downgrade returns to. Named
#: rather than `-1` so the downgrade test says which schema it expects to land
#: in, and fails visibly if a third revision is inserted between the two.
CORE_SCHEMA = "0001_core_schema"


def _upgrade_to(engine: Engine, revision: str) -> None:
    command.upgrade(_config_for(engine), revision)


def _insert_run(engine: Engine) -> int:
    with engine.connect() as connection:
        run_id = connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(scenario_type, parameters, seed, started_at) "
                "VALUES ('replay-only', '{}'::jsonb, 0, now()) RETURNING id"
            )
        ).scalar_one()
        connection.commit()
    return int(run_id)


def _completed_at(engine: Engine, run_id: int) -> object:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT completed_at FROM scenario_runs WHERE id = :id"),
            {"id": run_id},
        ).scalar_one()


def test_scenario_runs_carries_a_nullable_completed_at(
    empty_database: Engine,
) -> None:
    """Nullable, timezone-aware, and with no default of any kind.

    All three properties are the column's meaning rather than its style. A NOT
    NULL would make a run unwritable until it had finished; a server default
    would stamp every row complete at the moment it was created, which records
    an intention rather than an outcome; and a naive timestamp would record a
    completion time whose clock nobody can identify afterwards.
    """
    # spec: db-007
    _upgrade(empty_database)

    column = _columns(empty_database, "scenario_runs")["completed_at"]

    assert column["nullable"] is True
    assert column["default"] is None
    assert isinstance(column["type"], DateTime)
    assert column["type"].timezone is True


def test_the_completion_revision_does_not_backfill_existing_runs(
    empty_database: Engine,
) -> None:
    """The named failure case: a run that predates the column stays unknown.

    Backfilling is the tempting move, because it leaves no nulls behind. It is
    also exactly wrong here: the rows already in the database are the runs
    whose completion nobody recorded, so stamping them complete would erase the
    only evidence that the question is open.
    """
    # spec: db-007
    _upgrade_to(empty_database, CORE_SCHEMA)
    run_id = _insert_run(empty_database)

    _upgrade(empty_database)

    assert _completed_at(empty_database, run_id) is None


def test_downgrading_the_completion_revision_drops_the_column(
    empty_database: Engine,
) -> None:
    # spec: db-007 -- the presence assertion before the downgrade is what makes
    # this fail while the column does not exist. Without it the test passes on
    # an unmigrated database, which is the shape of a test that proves nothing.
    _upgrade(empty_database)
    assert "completed_at" in _columns(empty_database, "scenario_runs")

    command.downgrade(_config_for(empty_database), CORE_SCHEMA)

    assert "completed_at" not in _columns(empty_database, "scenario_runs")
    assert "scenario_runs" in inspect(empty_database).get_table_names()


# Mutation results, 2026-09-04, for the two `db-007` assertions above that
# claim an *absence* and would otherwise pass against an empty change:
#
#   * adding `op.execute("UPDATE scenario_runs SET completed_at = now()")` to
#     the revision turned `..._does_not_backfill_existing_runs` red, and only
#     that one -- a backfill touches rows that already exist and is invisible
#     to every other test here;
#   * adding `server_default=sa.func.now()` to the column turned five tests
#     red across this file and `test_db_repository.py`, because a default is
#     visible both in the reflected column and in every run created afterwards.
#
# The pair is deliberate. A default and a backfill are the two ways the column
# acquires a value nobody asked for, they fail differently, and each is caught
# by a test that does not catch the other.


# ---------------------------------------------------------------------------
# db-010: observations indexed by the run that produced them.
#
# `observations` carried a primary key and a GiST index on location and
# nothing else, so `scenario_run_id` -- the column nearly every detection
# measurement filters on, and a foreign key declared ON DELETE CASCADE --
# had nothing behind it. At 20.7 million rows in 12 GB that made a single
# pass over the corpus three hundred sequential scans of the whole table.
#
# An unindexed column still returns correct answers, which is exactly why
# this is asserted rather than left to be noticed: nothing fails, it is
# merely slow enough to change what work is practical.
# ---------------------------------------------------------------------------


def test_observations_are_indexed_by_scenario_run(empty_database: Engine) -> None:
    # spec: db-010, db-001
    _upgrade(empty_database)

    with empty_database.connect() as connection:
        definitions = (
            connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename = 'observations'"
                )
            )
            .scalars()
            .all()
        )

    assert any(
        "scenario_run_id" in definition and "USING btree" in definition
        for definition in definitions
    ), f"no btree index on observations.scenario_run_id: {definitions}"


def test_selecting_one_runs_observations_does_not_scan_the_table(
    empty_database: Engine,
) -> None:
    """The index is only worth having if the planner will use it, and that is
    a different claim from its existence -- a planner that still chooses a
    sequential scan leaves the measurement exactly as slow as before."""
    # spec: db-010, NFR-602
    _upgrade(empty_database)

    with empty_database.connect() as connection:
        # The planner prefers a sequential scan on a tiny table whatever the
        # indexes say, and the test database is tiny. Disabling the choice is
        # what makes this a test of the index rather than of the row count.
        connection.execute(text("SET enable_seqscan = off"))
        plan = "\n".join(
            connection.execute(
                text("EXPLAIN SELECT id FROM observations " "WHERE scenario_run_id = 1")
            )
            .scalars()
            .all()
        )

    assert "Index" in plan, f"planner will not use an index on one run: {plan}"
