"""Shared fixtures.

Entering `TestClient(app)` runs the lifespan, which builds the Engine, so
every test that does so needs `DATABASE_URL` set. The value points at a port
where nothing listens: constructing an Engine must not reach the host, so an
unreachable address is a stricter fixture than a working one -- if anything
in startup ever connects eagerly, these tests fail instead of quietly
acquiring a Docker dependency.

Tests that need the *absence* of the variable override this with
`monkeypatch.delenv`, which takes precedence for the duration of that test.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.db import session as db_session

UNREACHABLE_URL = "postgresql+psycopg://nobody@127.0.0.1:1/none"

#: The application's real database, captured **at import** and never read
#: from the environment again. The autouse fixture below replaces
#: `DATABASE_URL` with an unreachable address for every test, so a guard
#: reading the environment when it runs compares against the placeholder and
#: waves the real database through. That is not hypothetical: the first
#: version of `_guarded` did exactly this, passed all ten of its own unit
#: tests, and then failed to stop the command that destroyed the corpus when
#: it was re-run deliberately to check.
APPLICATION_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    yield
    db_session.dispose_engine()


# --------------------------------------------------------------- database tier

#: Deliberately *not* `DATABASE_URL`. The tests gated on this create and drop
#: schema, so keying them on the application's own variable would eventually run
#: a `DROP` against whatever database a developer happened to have configured.
#: Two variables make that impossible by construction rather than by care.
TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"

requires_database = pytest.mark.skipif(
    not os.environ.get(TEST_DATABASE_URL_ENV, "").strip(),
    reason=f"{TEST_DATABASE_URL_ENV} is unset; skipping the live-database tier",
)


#: How much a test fixture could plausibly have put there. Fixtures insert a
#: run or two; one generated run alone holds tens of thousands of
#: observations and one batch is twenty runs. Nothing legitimate sits in
#: between, so these are set nowhere near either edge rather than tuned.
MAX_FIXTURE_RUNS = 20
MAX_FIXTURE_OBSERVATIONS = 10_000


class DatabaseGuardError(RuntimeError):
    """The database tier was pointed somewhere it must not drop."""


def same_database(one: str, other: str) -> bool:
    """Do two URLs name the same database on the same server?

    Host, port and database only. Credentials and driver are excluded
    deliberately: the same database reached as a different user over a
    different driver is still the same database, and a guard that compared
    whole URL strings would wave that through -- which is the obvious
    implementation and the wrong one.
    """
    from sqlalchemy.engine import make_url

    a, b = make_url(one), make_url(other)
    return (a.host, a.port, a.database) == (b.host, b.port, b.database)


def guard_population(*, runs: int, observations: int, url: str) -> None:
    """Refuse to drop a database that is holding more than a test's worth.

    **This is the check that matters**, and `same_database` is the cheap one
    beside it. Identity compares spellings, and one database reached as
    `localhost` and as a container hostname is two spellings of one
    disaster. Counting what is actually there does not care how the database
    was addressed.

    Named counts rather than a bare refusal, because the two situations a
    reader might be in -- pointed at the wrong database, or a test left
    something behind -- look identical until the numbers are printed.
    """
    from sqlalchemy.engine import make_url

    if runs <= MAX_FIXTURE_RUNS and observations <= MAX_FIXTURE_OBSERVATIONS:
        return
    name = make_url(url).database
    raise DatabaseGuardError(
        f"refusing to drop the schema of {name!r}: it holds {runs:,} scenario "
        f"runs and {observations:,} observations, which is more than a test "
        f"fixture creates (at most {MAX_FIXTURE_RUNS} runs and "
        f"{MAX_FIXTURE_OBSERVATIONS:,} observations). This looks like a "
        "generated corpus rather than a test database. Point "
        f"{TEST_DATABASE_URL_ENV} at a database of its own -- `make "
        "test-backend` provisions one -- or clear this database deliberately "
        "if it really is disposable. A corpus was destroyed exactly here once."
    )


def _guarded(engine: Engine) -> None:
    """Both checks, run before anything is dropped."""
    url = engine.url.render_as_string(hide_password=False)
    if APPLICATION_DATABASE_URL and same_database(url, APPLICATION_DATABASE_URL):
        raise DatabaseGuardError(
            f"{TEST_DATABASE_URL_ENV} names the same database as DATABASE_URL "
            f"({make_url(url).database!r} on {make_url(url).host}). The tier "
            "below drops the schema, so this would destroy the application's "
            "own data. `make test-backend` provisions a separate database; a "
            "hand-written `docker compose run` does not."
        )
    with engine.connect() as connection:
        runs, observations = 0, 0
        for table, column in (("scenario_runs", "runs"), ("observations", "obs")):
            try:
                count = int(
                    connection.execute(
                        text(f"SELECT count(*) FROM {table}")
                    ).scalar_one()
                )
            except Exception:
                # No such table: an empty or unmigrated database, which is
                # exactly what this tier expects to find.
                connection.rollback()
                continue
            if column == "runs":
                runs = count
            else:
                observations = count
    guard_population(runs=runs, observations=observations, url=url)


def live_database_url() -> str:
    """The live test database's URL, for fixtures that have already skipped."""
    url = os.environ.get(TEST_DATABASE_URL_ENV, "").strip()
    if not url:  # pragma: no cover -- unreachable behind `requires_database`
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is unset")
    return url


@pytest.fixture
def empty_database() -> Iterator[Engine]:
    """An empty schema with PostGIS available, torn down after the test.

    Every migration test starts from genuinely empty rather than from
    whatever the previous test left, because "applies cleanly from empty" is
    the property under test and a partially-migrated database would prove a
    weaker one. Dropping and recreating `public` is enough, and is far faster
    than dropping the database itself.

    The extension is recreated here rather than by a migration: `db-001`
    requires a *missing* extension to fail loudly at migration time, so the
    migrations must assert it and not create it. Creating it is the
    container image's job for the real database, and this fixture's for the
    test one.
    """
    engine = create_engine(live_database_url(), poolclass=NullPool)
    _guarded(engine)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.commit()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def database_without_postgis() -> Iterator[Engine]:
    """An empty schema with the extension deliberately absent."""
    engine = create_engine(live_database_url(), poolclass=NullPool)
    _guarded(engine)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()
    try:
        yield engine
    finally:
        engine.dispose()
