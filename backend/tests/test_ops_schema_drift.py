"""The health signal refuses when the schema is behind the code. Spec: ops-005.

**The defect of record lasted a day and nothing could see it.** `api-012` added
two columns in `0009`; the fixture that brings the test database to head applied
them before every database-tier test, and nobody applied them to the application's
database. So `/api/v1/operational-picture` returned 500 from the moment that item
landed, 1,874 tests passed over those columns, `docker compose ps` reported the
backend **healthy**, and `/api/v1/health` answered 200 throughout -- because
`api-001` deliberately has it touch no table.

Three groups.

**The expectation, which must come from the migrations and never from the
database.** Read out of `alembic_version` -- the table being checked -- the
comparison agrees with itself on every database, which is a guard that cannot
fail and therefore is not one.

**Three states and not two.** At head answers 200; drifted refuses with 503 and
names both revisions; *unreachable* answers **200** and says it could not tell.
The third is the whole of what keeps `api-001`'s guarantee: an outage is not a
misconfiguration, and refusing on one turns a degraded database into an
unreachable service, which is the failure that route was written to avoid. This is
also why the check cannot be a startup gate -- `db-005` opens no connection at
startup on purpose, and determining a revision needs one.

**A guard that fires routinely is one somebody switches off.** Nothing applies
migrations when the stack starts, so without the Makefile half of this item every
first run would sit unhealthy until somebody ran `migrate`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.health import get_sessions
from app.db.migrations import (
    AT_HEAD,
    DRIFTED,
    UNKNOWN,
    alembic_config,
    compare_schema,
    expected_revision,
    heads_on_disk,
)
from app.db.repository import schema_state
from app.main import app
from tests.conftest import requires_database

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"

#: Native checkout, then the read-only mount `test-backend` adds -- Compose
#: mounts `./backend:/app`, so the root Makefile is not in the image.
#: `test_replay.py`'s idiom, and its argument: **skipping is not an option**,
#: because a structural guard that silently does not run is the failure one level
#: up from the one it is checking for.
MAKEFILE_PATHS = (BACKEND.parent / "Makefile", Path("/repo/Makefile"))


def _makefile() -> str:
    for path in MAKEFILE_PATHS:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise AssertionError(  # pragma: no cover -- a broken checkout or mount
        f"the Makefile is at none of {[str(p) for p in MAKEFILE_PATHS]}."
    )


def _revision_ids() -> set[str]:
    """Every revision id declared under `alembic/versions/`."""
    return {
        match.group(1)
        for path in VERSIONS.glob("[0-9]*.py")
        for match in [re.search(r'^revision = "([^"]+)"', path.read_text(), re.M)]
        if match
    }


def _script_dir(tmp_path: Path, *revisions: tuple[str, str | None]) -> Config:
    """An Alembic script directory holding exactly the revisions given."""
    root = tmp_path / "alembic"
    (root / "versions").mkdir(parents=True)
    (root / "script.py.mako").write_text("")
    (root / "env.py").write_text("")
    for name, down in revisions:
        down_str = "None" if down is None else f'"{down}"'
        (root / "versions" / f"{name}.py").write_text(
            f'revision = "{name}"\ndown_revision = {down_str}\n\n'
            "def upgrade() -> None: ...\n\n\ndef downgrade() -> None: ...\n"
        )
    config = Config()
    config.set_main_option("script_location", str(root))
    return config


class _ExplodingFactory:
    """A session factory whose connection attempt fails, as an outage does."""

    def begin(self) -> Any:
        raise RuntimeError("connection refused")

    def __call__(self) -> Any:  # pragma: no cover -- begin is the path used
        raise RuntimeError("connection refused")


class _CountingFactory:
    """Wraps a real factory and counts how many times it is read from."""

    def __init__(self, inner: sessionmaker) -> None:
        self.inner = inner
        self.reads = 0

    def begin(self) -> Any:
        self.reads += 1
        return self.inner.begin()


# ----------------------------------------------- the expectation, from disk


def test_the_project_has_exactly_one_head_and_it_is_a_real_revision() -> None:
    # spec: ops-005 -- the comparison is meaningless when "head" names two
    # things, so the single-head property is asserted on the real migrations
    # rather than assumed. Matched against the ids declared in the revision
    # files rather than pinned to a value, which would fail on every new
    # migration and teach somebody to delete the test.
    heads = heads_on_disk(alembic_config())

    assert len(heads) == 1
    assert heads[0] in _revision_ids()
    assert expected_revision() == heads[0]


def test_a_second_head_is_not_an_expectation(tmp_path: Path) -> None:
    # spec: ops-005 -- two revisions sharing a parent is a broken migration
    # graph, and "which revision should the database be at" then has no answer.
    # Reported as no expectation rather than as whichever head sorted first.
    config = _script_dir(
        tmp_path, ("0001_base", None), ("0002_a", "0001_base"), ("0002_b", "0001_base")
    )

    assert len(heads_on_disk(config)) == 2


def test_the_expectation_has_no_answer_when_the_graph_has_two_heads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: ops-005 -- found by the mutation pass, which is the point of running
    # one. `heads_on_disk` returning two was asserted above and `compare_schema`
    # refusing on two was asserted below, and **nothing tested the function
    # between them**: with two heads it returned whichever sorted first, so an
    # unreachable database would have reported a bogus expectation beside its
    # "could not tell". A test on each end of a chain is not a test of the chain.
    from app.db import migrations

    monkeypatch.setattr(
        migrations, "heads_on_disk", lambda _config: ("0002_a", "0002_b")
    )
    migrations.expected_revision.cache_clear()
    try:
        assert migrations.expected_revision() is None
    finally:
        # The real value is cached for the life of the process, so it has to be
        # recomputed before anything else reads it.
        migrations.expected_revision.cache_clear()


def test_no_migrations_at_all_is_not_an_expectation(tmp_path: Path) -> None:
    # spec: ops-005 -- the empty case, which must not read as "anything goes".
    config = _script_dir(tmp_path)

    assert heads_on_disk(config) == ()


# ------------------------------------------------------- the three states


def test_a_database_at_the_expected_revision_is_at_head() -> None:
    # spec: ops-005
    state = compare_schema(("0009_x",), "0009_x")

    assert state.status == AT_HEAD
    assert state.healthy


def test_a_database_one_revision_behind_is_drifted_and_names_both() -> None:
    # spec: ops-005, api-012 -- the defect of record, in miniature. Both
    # revisions are in the message because the operator's next action is
    # deciding whether to migrate or to roll the code back, and neither
    # revision alone answers that.
    state = compare_schema(
        ("0009_detection_pass_stamp",), "0008_detection_finding_policy"
    )

    assert state.status == DRIFTED
    assert not state.healthy
    assert state.expected == "0009_detection_pass_stamp"
    assert state.found == "0008_detection_finding_policy"
    assert "0009_detection_pass_stamp" in state.detail
    assert "0008_detection_finding_policy" in state.detail


def test_a_database_ahead_of_the_code_is_drifted_too() -> None:
    # spec: ops-005 -- somebody deployed newer code and rolled back, so this
    # code may read columns that no longer exist. Refused in both directions,
    # and the detail has to say which way round it is or the operator migrates
    # a database that is already further on than the code.
    state = compare_schema(("0008_old",), "0009_newer")

    assert state.status == DRIFTED
    assert state.expected == "0008_old"
    assert state.found == "0009_newer"
    assert "ahead" in state.detail.lower()


def test_a_database_nobody_has_migrated_is_drifted_and_not_unknown() -> None:
    # spec: ops-005 -- an absent or empty version table is a database nobody
    # has migrated, which is a deployment that has not finished rather than a
    # database that cannot be read. Reported as unknown it would answer 200 and
    # the stack would look fine with no schema at all.
    state = compare_schema(("0009_x",), None)

    assert state.status == DRIFTED
    assert state.found is None
    assert "never" in state.detail.lower() or "no revision" in state.detail.lower()


def test_two_heads_refuse_rather_than_pass_whatever_the_database_says() -> None:
    # spec: ops-005 -- with no single expectation there is nothing to compare
    # against, and passing would mean a broken migration graph reads as healthy.
    state = compare_schema(("0002_a", "0002_b"), "0002_a")

    assert state.status == DRIFTED
    assert state.expected is None


def test_a_database_that_cannot_be_reached_is_unknown_and_still_healthy() -> None:
    # spec: ops-005, api-001 -- the guarantee this item must not break. An
    # outage is not a misconfiguration; refusing here would turn a degraded
    # database into an unreachable service, which is the failure `api-001` was
    # written to avoid and the reason this is not a startup gate.
    state = schema_state(_ExplodingFactory())  # type: ignore[arg-type]

    assert state.status == UNKNOWN
    assert state.healthy
    assert state.found is None


def test_no_engine_at_all_is_unknown_rather_than_an_error() -> None:
    # spec: ops-005, db-005 -- `get_sessionmaker` raises before the lifespan has
    # run, and health has to answer in that state: it answers before persistence
    # exists, which is `api-001`'s whole point.
    state = schema_state(None)

    assert state.status == UNKNOWN
    assert state.healthy


# ------------------------------------------------------------- the route


def _override(state_factory: Any) -> None:
    app.dependency_overrides[get_sessions] = lambda: state_factory


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    app.dependency_overrides.clear()


def test_the_route_answers_200_and_names_the_revision_at_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: ops-005, api-001 -- the ordinary case, and the body carries the
    # revision so an operator reading it knows what "healthy" was measured
    # against rather than taking the word for it.
    from app.api.v1 import health as health_route

    monkeypatch.setattr(
        health_route,
        "schema_state",
        lambda _sessions: compare_schema(("0009_x",), "0009_x"),
    )
    _override(object())

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["schema"] == AT_HEAD
    assert body["expected"] == "0009_x"
    assert body["found"] == "0009_x"


def test_the_route_refuses_with_503_when_the_schema_has_drifted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: ops-005 -- 503 and not a 200 carrying a sad field, because the thing
    # that was silent is the container probe: it runs `urlopen` against this
    # path and only a non-2xx makes the container report unhealthy. A body
    # nobody parses is what we already had.
    from app.api.v1 import health as health_route

    monkeypatch.setattr(
        health_route,
        "schema_state",
        lambda _sessions: compare_schema(("0009_new",), "0008_old"),
    )
    _override(object())

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["schema"] == DRIFTED
    assert body["expected"] == "0009_new"
    assert body["found"] == "0008_old"
    assert "0008_old" in body["detail"]


def test_the_route_answers_200_when_it_cannot_tell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: ops-005, api-001 -- the carve-out stated as a test rather than as a
    # sentence. A database that is down must not make the service look dead.
    from app.api.v1 import health as health_route

    monkeypatch.setattr(
        health_route, "schema_state", lambda _sessions: schema_state(None)
    )
    _override(None)

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["schema"] == UNKNOWN


def test_the_route_carries_exactly_these_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: ops-005, api-009 -- the key set asserted exactly rather than by
    # substring, so a field cannot quietly disappear and so a reader of the
    # body knows the shape is the same in all three states.
    from app.api.v1 import health as health_route

    for heads, found in ((("0009_x",), "0009_x"), (("0009_x",), "0008_y"), ((), None)):
        monkeypatch.setattr(
            health_route,
            "schema_state",
            lambda _s, h=heads, f=found: compare_schema(h, f),
        )
        _override(object())

        body = TestClient(app).get("/api/v1/health").json()

        assert set(body) == {"status", "schema", "expected", "found", "detail"}


def test_the_route_still_answers_with_no_database_configured() -> None:
    # spec: api-001 -- its own failure case, unviolated and asserted here
    # because this item is the one that could have broken it. Nothing is
    # overridden and no lifespan has run, so there is no engine at all.
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200


# ------------------------------------------- recovery, and the first run


@requires_database
def test_the_revision_is_read_on_every_probe_so_a_live_migration_clears_it(
    factory: sessionmaker,
) -> None:
    # spec: ops-005 -- the reason the database side is not cached. Somebody runs
    # `make migrate` against a running stack, and the container has to go
    # healthy on the next probe rather than needing a restart; cached, the
    # refusal would outlive the thing it was reporting.
    counting = _CountingFactory(factory)

    schema_state(counting)  # type: ignore[arg-type]
    schema_state(counting)  # type: ignore[arg-type]

    assert counting.reads == 2


def test_starting_the_stack_applies_the_migrations_first() -> None:
    # spec: ops-005, ops-003 -- a guard that fires on every first run is one
    # somebody switches off. Nothing applies migrations on start, so without
    # this the check would make a freshly built stack permanently unhealthy and
    # the rational response would be to delete the check.
    makefile = _makefile()

    for target in ("up", "demo"):
        line = next(
            row for row in makefile.splitlines() if re.match(rf"^{target}:", row)
        )
        assert "migrate" in line.split("##")[0], f"`{target}` does not migrate first"


# ------------------------------------------------------ against a database


@requires_database
def test_a_live_database_at_head_reports_at_head(factory: sessionmaker) -> None:
    # spec: ops-005 -- `migrated_database` brings the schema to head, which is
    # the state every deployment is supposed to be in.
    state = schema_state(factory)

    assert state.status == AT_HEAD
    assert state.found == expected_revision()


@requires_database
def test_a_live_database_with_no_version_table_is_drifted(
    empty_database: Engine,
) -> None:
    # spec: ops-005 -- a database nobody has migrated, which is what a fresh
    # machine looks like between `up` and `migrate`.
    state = schema_state(sessionmaker(bind=empty_database, autoflush=False))

    assert state.status == DRIFTED
    assert state.found is None


@requires_database
def test_a_version_table_holding_no_row_is_drifted(factory: sessionmaker) -> None:
    # spec: ops-005 -- the table exists and names no revision, which is not the
    # same as the table being absent and is the same conclusion: nobody has
    # migrated this. Reported as at-head it would be the quietest possible
    # version of the defect this item exists for.
    with factory.begin() as session:
        session.execute(text("DELETE FROM alembic_version"))

    state = schema_state(factory)

    assert state.status == DRIFTED
    assert state.found is None


@requires_database
def test_the_live_route_refuses_against_a_database_one_revision_behind(
    factory: sessionmaker,
) -> None:
    # spec: ops-005 -- the whole item, end to end, against the exact condition
    # that cost a day: a real database one revision back from the code. Done by
    # moving the database rather than by faking a revision, so the thing under
    # test is the comparison a deployment would actually make.
    from alembic import command

    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", factory.kw["bind"].url.render_as_string(hide_password=False)
    )
    command.downgrade(config, "-1")
    _override(factory)

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["schema"] == DRIFTED
    assert body["expected"] == expected_revision()
    assert body["found"] != body["expected"]
