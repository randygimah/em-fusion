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
from sqlalchemy.pool import NullPool

from app.db import session as db_session

UNREACHABLE_URL = "postgresql+psycopg://nobody@127.0.0.1:1/none"


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
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()
    try:
        yield engine
    finally:
        engine.dispose()
