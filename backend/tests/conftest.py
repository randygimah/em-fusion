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

from collections.abc import Iterator

import pytest

from app.db import session as db_session

UNREACHABLE_URL = "postgresql+psycopg://nobody@127.0.0.1:1/none"


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    yield
    db_session.dispose_engine()
