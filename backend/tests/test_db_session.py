"""Database connectivity: engine, session, and configuration.

Every test here proves `db-005`, and every one of them runs without a
database. That is the property the item exists to preserve: engine
construction is lazy and opens no connection, so the unit suite stays
runnable on a machine with no Docker and `db-001`'s live-database tests are
the only ones that need the `postgis` service.

Two of the URLs below point at 127.0.0.1 port 1, where nothing listens. That
is deliberate and load-bearing rather than lazy fixture-writing: if
constructing an `Engine` reached the host, these tests would raise instead of
passing, so an unreachable address is itself the assertion that no connection
was made.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db import session as db_session
from app.db.session import EngineNotInitialisedError, MissingDatabaseUrlError
from app.main import app

# Nothing listens on port 1. Constructing an Engine against this must succeed;
# opening a connection to it cannot.
UNREACHABLE_URL = "postgresql+psycopg://nobody@127.0.0.1:1/none"

APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(autouse=True)
def _no_leftover_engine() -> Iterator[None]:
    """No Engine outlives a test.

    The item requires exactly one Engine per process, which makes the engine
    module-level state. Left in place it would leak between tests and turn
    the "same object" assertions into accidents of ordering.
    """
    db_session.dispose_engine()
    yield
    db_session.dispose_engine()


class RecordingSession:
    """A stand-in for a Session that records what the dependency did to it.

    The rollback-on-exception guarantee is about control flow, not about SQL,
    so it is provable without a database -- and has to be, because the failure
    it guards against is a handler raising, which no happy-path integration
    test would reach.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


def _python_sources(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of every Constant that is a docstring.

    Read the note in `test_adp_opensky.py` before deleting this: a source-text
    check on this file failed the moment an implementation docstring explained
    the rule it was enforcing. A docstring that *documents* the DSN form is
    documentation; a string literal the code could connect with is the defect.
    """
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return docstrings


# --------------------------------------------------------------- configuration


def test_missing_database_url_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: db-005 -- delenv is explicit because conftest sets the variable for
    # every test; without it this would assert against the fixture, not absence
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(MissingDatabaseUrlError, match="DATABASE_URL"):
        db_session.database_url()


def test_empty_database_url_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: db-005 -- an empty value is a missing value, not a default
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(MissingDatabaseUrlError, match="DATABASE_URL"):
        db_session.database_url()


def test_whitespace_database_url_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: db-005
    monkeypatch.setenv("DATABASE_URL", "   ")
    with pytest.raises(MissingDatabaseUrlError, match="DATABASE_URL"):
        db_session.database_url()


def test_database_url_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    assert db_session.database_url() == UNREACHABLE_URL


def test_startup_fails_when_database_url_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005 -- loud at startup, not at first query
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(MissingDatabaseUrlError, match="DATABASE_URL"):
        with TestClient(app):
            pass  # pragma: no cover -- startup must raise before the body runs


# ---------------------------------------------------------------------- engine


def test_engine_construction_opens_no_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    engine = db_session.init_engine()

    connects: list[object] = []
    event.listen(engine, "connect", lambda *args: connects.append(args))

    db_session.get_sessionmaker()

    assert connects == []
    assert engine.pool.checkedin() == 0
    assert engine.pool.checkedout() == 0


def test_engine_construction_does_not_reach_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005 -- an unreachable URL constructs cleanly; only a query fails
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    assert db_session.init_engine() is not None


def test_engine_uses_the_psycopg3_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: db-005 -- postgresql+psycopg, not psycopg2 and not the default
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    engine = db_session.init_engine()
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_exactly_one_engine_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: db-005 -- the pool is shared, not rebuilt
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    first = db_session.init_engine()
    assert db_session.init_engine() is first
    assert db_session.get_engine() is first
    assert db_session.get_engine() is first


def test_get_engine_before_startup_fails_loudly() -> None:
    # spec: db-005 -- no lazy self-construction outside the lifespan hook
    with pytest.raises(EngineNotInitialisedError):
        db_session.get_engine()


def test_get_sessionmaker_before_startup_fails_loudly() -> None:
    # spec: db-005 -- the sibling of the check above. Written after the
    # implementation, to close the one uncovered branch: get_engine had this
    # path asserted and get_sessionmaker did not, which is exactly the asymmetry
    # a coverage report exists to surface.
    with pytest.raises(EngineNotInitialisedError):
        db_session.get_sessionmaker()


def test_dispose_engine_releases_and_clears_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    db_session.init_engine()
    db_session.dispose_engine()
    with pytest.raises(EngineNotInitialisedError):
        db_session.get_engine()


def test_dispose_engine_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: db-005 -- shutdown after shutdown, and after a failed startup,
    # must not raise. Written as a full cycle rather than two bare calls: a
    # no-op satisfies two bare calls, which makes them assert nothing.
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    db_session.init_engine()
    db_session.dispose_engine()
    db_session.dispose_engine()
    with pytest.raises(EngineNotInitialisedError):
        db_session.get_engine()


def test_sessionmaker_is_bound_to_the_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: db-005
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    engine = db_session.init_engine()
    assert db_session.get_sessionmaker().kw["bind"] is engine


def test_lifespan_creates_the_engine_and_disposes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    with TestClient(app):
        assert db_session.get_engine() is not None
    with pytest.raises(EngineNotInitialisedError):
        db_session.get_engine()


# ------------------------------------------------------------------- session


def test_session_dependency_yields_one_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005
    recorded = RecordingSession()
    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: lambda: recorded)

    generator = db_session.get_session()
    assert next(generator) is recorded
    with pytest.raises(StopIteration):
        next(generator)


def test_session_dependency_closes_on_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005 -- and does not commit; the unit of work is the repository's
    recorded = RecordingSession()
    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: lambda: recorded)

    generator = db_session.get_session()
    next(generator)
    with pytest.raises(StopIteration):
        next(generator)

    assert recorded.calls == ["close"]


def test_session_dependency_rolls_back_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005 -- no session left open, no transaction left uncommitted
    recorded = RecordingSession()
    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: lambda: recorded)

    generator = db_session.get_session()
    next(generator)
    with pytest.raises(RuntimeError, match="handler failed"):
        generator.throw(RuntimeError("handler failed"))

    assert recorded.calls == ["rollback", "close"]


# --------------------------------------------------------------- api-001 held


def test_health_answers_without_acquiring_a_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: db-005, api-001 -- a degraded database must not present as an
    # unreachable service
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    with TestClient(app) as client:
        connects: list[object] = []
        event.listen(db_session.get_engine(), "connect", lambda *a: connects.append(a))
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert connects == []


# ------------------------------------------------------------ structural rules


def test_no_engine_is_constructed_outside_the_db_module() -> None:
    """One Engine per process, and `app/db/` is the only place that makes it.

    This asserts an absence, so it cannot fail while the violation does not
    exist -- the exact shape of test that passed vacuously against an empty
    stub once already. Mutation-tested 2026-08-27 instead: adding both
    `from sqlalchemy import create_engine` and a `create_engine(...)` call to
    `app/api/v1/health.py` turned it red, and removing them turned it green.
    Both forms are checked because catching only the call would miss an alias
    and catching only the import would miss `sqlalchemy.create_engine(...)`.
    """
    # spec: db-005 -- constructing an Engine in a request handler fails the spec
    offenders: list[str] = []
    for path in _python_sources(APP_DIR):
        if path.parent.name == "db":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr if isinstance(func, ast.Attribute) else ""
                )
                if name == "create_engine":
                    offenders.append(f"{path.name}:{node.lineno} calls create_engine")
            elif isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy":
                for alias in node.names:
                    if alias.name == "create_engine":
                        offenders.append(f"{path.name}:{node.lineno} imports it")

    assert offenders == []


def test_no_dsn_literal_in_application_source() -> None:
    """No hardcoded fallback connection string anywhere under `app/`.

    Also an absence assertion, and mutation-tested the same way on
    2026-08-27: a module-level `FALLBACK = "postgresql+psycopg://..."` in
    `app/api/v1/health.py` turned it red. A third mutation checked the
    opposite direction -- the same DSN inside a *docstring* left it green,
    which is what `_docstring_nodes` is for. Without that exclusion the test
    would forbid documenting the URL format in the module that reads it,
    which is how the adapter's import-direction check first broke.
    """
    # spec: db-005, NFR-401 -- the URL comes from the environment only
    schemes = ("postgresql://", "postgresql+psycopg://", "postgres://")
    offenders: list[str] = []
    for path in _python_sources(APP_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and any(scheme in node.value for scheme in schemes)
            ):
                offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == []
