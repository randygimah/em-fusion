"""Engine, sessionmaker, and the per-request Session dependency. Spec: db-005.

Three properties here are load-bearing, and each exists because the obvious
alternative fails in a way that is hard to see afterwards.

**One Engine per process.** The Engine owns the connection pool, so building
one per request would rebuild the pool per request and turn a pooled
connection back into a fresh PostgreSQL handshake and a forked server
process. It is created once in the application lifespan and disposed on
shutdown; `get_engine` refuses rather than lazily building one, so a caller
that reaches for the Engine outside the lifespan gets an error instead of a
second pool nobody knows about.

**Construction opens no connection.** `create_engine` only resolves the
dialect and driver, so the whole unit suite runs without a database and
`db-001`'s live-database tests stay the only ones that need the `postgis`
service. That is a property worth protecting deliberately: the moment
something here connects eagerly, every test in the repository acquires a
Docker dependency.

**The dependency closes but does not commit.** Committing here would make the
request boundary the unit of work, and `dal-002` requires the unit of work to
be one `save_batch` call -- observations and quarantine records together, or
neither. A request-scoped commit would split that guarantee in two without
any visible failure.

The URL is read from the environment only (NFR-401). The form Compose passes
is `postgresql+psycopg://user:password@host:5432/database` -- psycopg 3, not
psycopg2, which SQLAlchemy would otherwise select for a bare `postgresql://`.
There is deliberately no default: a fallback DSN would let the application
start against the wrong database and report itself healthy.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL_ENV = "DATABASE_URL"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class MissingDatabaseUrlError(RuntimeError):
    """DATABASE_URL is absent or empty.

    A distinct type rather than a bare RuntimeError so a test can assert this
    specific failure. `NotImplementedError` subclasses `RuntimeError`, which
    made an earlier version of the test pass against an unimplemented stub.
    """


class EngineNotInitialisedError(RuntimeError):
    """The Engine was asked for outside the application lifespan."""


def database_url() -> str:
    """The configured URL, or a loud failure.

    Whitespace-only counts as absent: a trailing newline in a `.env` file is
    a realistic way to produce one, and an empty URL fails far less clearly
    at first query than it does here.
    """
    url = os.environ.get(DATABASE_URL_ENV, "").strip()
    if not url:
        raise MissingDatabaseUrlError(
            f"{DATABASE_URL_ENV} is not set. It is required at startup and has "
            "no default, so the application cannot silently connect elsewhere."
        )
    return url


def init_engine() -> Engine:
    """Create the process-wide Engine, or return the existing one.

    Idempotent rather than raising on a second call, so a test client entered
    twice, or a worker that re-runs startup, reuses the pool instead of
    leaking one.
    """
    global _engine, _session_factory

    if _engine is not None:
        return _engine

    _engine = create_engine(database_url(), pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine, autoflush=False)
    return _engine


def get_engine() -> Engine:
    """The process-wide Engine. Never builds one -- see the module docstring."""
    if _engine is None:
        raise EngineNotInitialisedError(
            "No Engine. init_engine() runs in the application lifespan; "
            "callers outside it must not construct their own."
        )
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """The factory bound to the process-wide Engine."""
    if _session_factory is None:
        raise EngineNotInitialisedError(
            "No sessionmaker. init_engine() runs in the application lifespan."
        )
    return _session_factory


def dispose_engine() -> None:
    """Release the pool and forget the Engine.

    Safe to call when there is nothing to dispose, because shutdown runs after
    a failed startup too and an error there would mask the one that mattered.
    """
    global _engine, _session_factory

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one Session per request.

    Rolls back when the handler raises, and closes either way, so a failed
    request leaves no session open and no transaction uncommitted.
    """
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
