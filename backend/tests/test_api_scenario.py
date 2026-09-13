"""The scenario control endpoints. Spec: api-006.

Two endpoints, not three. `POST /scenario/reset` is deferred to its own item
and its control stays disabled on screen: a run is a row, `db-007` records that
nothing is ever deleted, and "a cleared run state" has no honest meaning until
a batch can be in flight and abandoned.

**Start is tested without a corpus and without a database.** The batch launcher
is injected precisely so these tests can substitute one that records its
argument, which is what lets the refusals be asserted as *nothing was started*
rather than as an error message. The listing half needs real rows and sits in
the database tier.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import NullPool

from alembic import command
from app.api.v1.scenario import get_batch_launcher
from app.api.v1.schemas.scenario import BatchRequest
from app.dal.models import ScenarioRunSummary
from app.db.migrations import alembic_config
from app.main import app
from app.pipeline import MAX_RUNS, MIN_RUNS
from app.replay import MANIFEST_NAME
from app.scenario import batch
from app.scenario.incident import IncidentParameters, ScenarioType
from app.scenario.seeding import SEED_MAX
from tests.conftest import live_database_url, requires_database

HOUR_START = datetime(2022, 6, 27, 12, 0, tzinfo=UTC)


def _batch_request() -> BatchRequest:
    return BatchRequest(
        scenario_type=ScenarioType.GNSS_DEGRADATION,
        base_seed=20220627,
        runs=MIN_RUNS,
        duration_seconds=900,
        incident=IncidentParameters(),
    )


CONFIGURATION: dict[str, Any] = {
    "scenarioType": "gnss-degradation",
    "baseSeed": 20220627,
    "runs": MIN_RUNS,
    "durationSeconds": 900,
    "incidentOffsetS": 120,
    "incidentDurationS": 300,
    "radiusKm": 60,
    "elevationDb": 8,
    "spectralExtent": "narrowband",
}


class RecordingLauncher:
    """Stands in for the thing that actually runs a batch.

    Records rather than runs, so a test can assert a refusal started nothing.
    """

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def __call__(self, request: Any) -> None:
        self.calls.append(request)


def _post(body: dict[str, Any]) -> tuple[int, dict[str, Any], RecordingLauncher]:
    launcher = RecordingLauncher()
    app.dependency_overrides[get_batch_launcher] = lambda: launcher
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/scenario/start", json=body)
    finally:
        app.dependency_overrides.pop(get_batch_launcher, None)
    payload = response.json() if response.content else {}
    return response.status_code, payload, launcher


# --------------------------------------------------------------- starting one


def test_start_is_accepted_rather_than_awaited() -> None:
    """202, and a body that is an acceptance rather than an outcome.

    A 200 carrying a finished batch summary would mean the request blocked for
    about seventy seconds, which nginx's default proxy timeout cuts at sixty --
    passing in development and failing in the container.
    """
    # spec: api-006 (second decision), NFR-503
    status, body, launcher = _post(CONFIGURATION)

    assert status == 202
    assert len(launcher.calls) == 1
    assert "completed" not in body
    assert "outcomes" not in body


def test_start_echoes_the_base_seed_it_was_given() -> None:
    # spec: api-006 -- a run is reproducible from its record only if the seed
    # that produced it is the seed the caller is told about
    _, body, _ = _post(CONFIGURATION)

    assert body["baseSeed"] == 20220627


def test_start_draws_a_seed_when_the_caller_omits_one() -> None:
    """The API draws it; the screen never invents one.

    `scn-004` settled that a seed the run record never saw is a run nobody can
    repeat, so the drawn value has to come back in the response.
    """
    # spec: api-006 (third decision), scn-004
    _, body, launcher = _post({**CONFIGURATION, "baseSeed": None})

    assert isinstance(body["baseSeed"], int)
    assert 0 <= body["baseSeed"] <= SEED_MAX
    assert launcher.calls[0].base_seed == body["baseSeed"]


def test_start_returns_one_distinct_seed_per_run() -> None:
    # spec: api-006 (third decision), scn-003 -- a caller would otherwise have
    # to wait for rows to learn which seeds its batch is using
    _, body, _ = _post(CONFIGURATION)

    assert len(body["seeds"]) == MIN_RUNS
    assert len(set(body["seeds"])) == MIN_RUNS


def test_start_hands_the_configuration_to_the_launcher() -> None:
    # spec: api-006 -- every dial the screen offers has to reach the batch, or
    # it is a control that changes nothing (scn-001's fourth failure case)
    _, _, launcher = _post(CONFIGURATION)

    sent = launcher.calls[0]
    assert sent.scenario_type.value == "gnss-degradation"
    assert sent.runs == MIN_RUNS
    assert sent.duration_seconds == 900
    assert sent.incident.start_offset_s == 120
    assert sent.incident.duration_s == 300
    assert sent.incident.radius_km == 60
    assert sent.incident.elevation_db == 8
    assert sent.incident.spectral_extent.value == "narrowband"


def test_an_unknown_scenario_type_is_refused_and_starts_nothing() -> None:
    # spec: api-006, FR-202 -- the original failure case on this item
    status, _, launcher = _post({**CONFIGURATION, "scenarioType": "sixth-type"})

    assert status == 422
    assert launcher.calls == []


def test_an_incident_that_begins_after_the_run_ends_is_refused() -> None:
    """Refused before anything starts, not inside the background batch.

    `run_batch` raises on this, but by then the request has returned 202 and
    the refusal survives only in a log. It is the defect that produced twenty
    mislabelled controls: every run claims a type and contains no incident.
    """
    # spec: api-006 (added failure case), scn-003
    status, _, launcher = _post(
        {**CONFIGURATION, "durationSeconds": 120, "incidentOffsetS": 120}
    )

    assert status == 422
    assert launcher.calls == []


@pytest.mark.parametrize("count", [MIN_RUNS - 1, MAX_RUNS + 1])
def test_a_batch_outside_the_run_bounds_is_refused(count: int) -> None:
    # spec: api-006 (added failure case), scn-003
    status, _, launcher = _post({**CONFIGURATION, "runs": count})

    assert status == 422
    assert launcher.calls == []


def test_the_run_summary_does_not_gain_recorded_parameters() -> None:
    """`api-002` serves this model too. Spec: api-006 (fourth decision).

    The recorded parameters carry the incident's radius, elevation, offset and
    duration. On the operational picture that would describe the staged
    incident to the analyst whose detectors are being measured against it.
    """
    # spec: api-006, api-009, api-002
    assert "parameters" not in ScenarioRunSummary.model_fields
    assert "ground_truth" not in ScenarioRunSummary.model_fields


# ------------------------------------------------------- against the database


@pytest.fixture
def scenario_database() -> Engine:
    """An empty schema brought to head. No runs: each test seeds its own."""
    engine = create_engine(live_database_url(), poolclass=NullPool)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.commit()
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        engine.dispose()


PARAMETERS = {
    "nominal_power_dbm": -95.0,
    "noise_sigma_db": 1.5,
    "nominal_snr_db": 20.0,
    "start_offset_s": 120,
    "duration_s": 300,
    "radius_km": 60.0,
    "elevation_db": 8.0,
    "spectral_extent": "narrowband",
    "start": "2022-06-27T12:00:00+00:00",
    "duration_seconds": 900,
}


def _insert_run(
    engine: Engine,
    run_id: int,
    *,
    seed: int,
    offset_s: int,
    completed: bool,
    ground_truth: str | None = None,
) -> None:
    with engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at, completed_at, "
                "ground_truth) VALUES (:id, 'gnss-degradation', "
                "CAST(:parameters AS jsonb), :seed, :started, :completed, "
                "CAST(:truth AS jsonb))"
            ),
            {
                "id": run_id,
                "parameters": __import__("json").dumps(PARAMETERS),
                "seed": seed,
                "started": HOUR_START + timedelta(seconds=offset_s),
                "completed": (
                    HOUR_START + timedelta(seconds=offset_s + 10) if completed else None
                ),
                "truth": ground_truth,
            },
        )
        connection.commit()


def _runs(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        response = client.get("/api/v1/scenario/runs")
    assert response.status_code == 200
    return list(response.json())


@pytest.mark.database
@requires_database
def test_the_runs_endpoint_is_empty_before_anything_has_run(
    scenario_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty list and a 200, not a 404. Spec: api-006.

    The same reasoning as `api-002`'s empty picture: a screen that cannot
    render until somebody has run a batch is a screen nobody can develop
    against.
    """
    # spec: api-006, api-002
    assert _runs(scenario_database, monkeypatch) == []


@pytest.mark.database
@requires_database
def test_the_runs_endpoint_lists_runs_newest_first(
    scenario_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-006 -- the screen's table is a recent-runs table
    _insert_run(scenario_database, 1, seed=11, offset_s=0, completed=True)
    _insert_run(scenario_database, 2, seed=22, offset_s=60, completed=True)
    _insert_run(scenario_database, 3, seed=33, offset_s=120, completed=False)

    listed = _runs(scenario_database, monkeypatch)

    assert [row["id"] for row in listed] == [3, 2, 1]
    assert [row["seed"] for row in listed] == [33, 22, 11]


@pytest.mark.database
@requires_database
def test_a_listed_run_carries_the_parameters_a_replay_needs(
    scenario_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Key for key, snake_case included. Spec: api-006 (fourth decision).

    The backend rebuilds a run from exactly these names and refuses a set
    carrying one it does not know, so a re-keying here would turn a replayable
    run into an unreplayable one at the point furthest from the mistake.
    """
    # spec: api-006, scn-004, scn-003
    _insert_run(scenario_database, 1, seed=11, offset_s=0, completed=True)

    listed = _runs(scenario_database, monkeypatch)

    assert listed[0]["parameters"] == PARAMETERS
    assert listed[0]["completedAt"] is not None
    assert listed[0]["scenarioType"] == "gnss-degradation"


@pytest.mark.database
@requires_database
def test_an_unfinished_run_is_listed_without_a_completion_stamp(
    scenario_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-006, db-007 -- absence is the informative state, and it covers
    # a run still going and a run that died; the row cannot tell them apart
    _insert_run(scenario_database, 1, seed=11, offset_s=0, completed=False)

    assert _runs(scenario_database, monkeypatch)[0]["completedAt"] is None


@pytest.mark.database
@requires_database
def test_a_listed_run_never_carries_the_answer_key(
    scenario_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`api-009`, asserted against a run that actually has one recorded.

    A test inserting no ground truth would pass against an endpoint that
    selects the column and serves it, which is the whole failure.
    """
    # spec: api-006, api-009
    _insert_run(
        scenario_database,
        1,
        seed=11,
        offset_s=0,
        completed=True,
        ground_truth='{"sensors": ["RF-01"], "aircraft": ["AC-0001"]}',
    )

    row = _runs(scenario_database, monkeypatch)[0]

    assert "groundTruth" not in row
    assert "ground_truth" not in row
    assert "RF-01" not in str(row)
    assert "AC-0001" not in str(row)


# ------------------------------------------------------------- the launcher
#
# Written after the implementation, which is a deviation from the order this
# project works in. The backend coverage gate is what named them: every other
# module in the tree sat at 100% and `app/scenario/batch.py` at 65%, with the
# uncovered lines being the whole of what the launcher actually does. Both
# assert claims the docstrings make and nothing else held.


class _InlineThread:
    """A Thread that runs its target on the calling thread.

    Lets the failure path be asserted without joining or sleeping. What it
    gives up is any claim about concurrency, so the construction arguments are
    asserted separately below.
    """

    def __init__(self, *, target: Any, name: str, daemon: bool) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        _InlineThread.last = self

    def start(self) -> None:
        self.target()


def test_a_failing_batch_is_logged_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """There is nobody left to raise to. Spec: api-006 (second decision).

    The response went out before this thread was scheduled, so an exception
    here has no caller. The rows already written are the record of what
    happened -- the same posture `run_batch` takes toward one run that fails
    inside a batch.
    """

    # spec: api-006, scn-003
    def explode(request: Any) -> None:
        raise RuntimeError("no corpus on disk")

    monkeypatch.setattr(batch, "Thread", _InlineThread)
    monkeypatch.setattr(batch, "run_batch_now", explode)

    with caplog.at_level("ERROR"):
        batch.launch_batch(_batch_request())

    assert "scenario batch failed" in caplog.text
    assert "no corpus on disk" in caplog.text
    assert _InlineThread.last.daemon is True


def test_the_batch_borrows_the_applications_engine_rather_than_building_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`db-003`: one Engine per process. Spec: api-006.

    A batch that called `init_engine` would build a second one and dispose the
    first out from under every in-flight request. The docstring claims this;
    this is what holds it.
    """
    # spec: api-006, db-003
    (tmp_path / MANIFEST_NAME).write_text("{}")
    seen: dict[str, Any] = {}

    def fake_run_batch(layout: Any, **kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(batch, "run_batch", fake_run_batch)
    monkeypatch.setattr(batch, "available_window", lambda manifest: "window")
    monkeypatch.setattr(batch, "load_layout", lambda: "layout")
    monkeypatch.setattr(batch, "load_exclusions", lambda path: frozenset())
    monkeypatch.setattr(
        batch.Pseudonymiser, "from_environment", classmethod(lambda cls: "pseudo")
    )
    monkeypatch.setattr(batch, "PostgisObservationRepository", lambda sessions: "repo")
    monkeypatch.setattr(batch, "get_sessionmaker", lambda: "sessions")

    batch.run_batch_now(_batch_request(), data_dir=tmp_path)

    assert seen["base_seed"] == 20220627
    assert seen["count"] == MIN_RUNS
    assert seen["duration_seconds"] == 900
    assert seen["incident"].start_offset_s == 120
    assert seen["session_factory"] == "sessions"


def test_the_launcher_never_builds_its_own_engine() -> None:
    """Asserted against the parsed code, not against the text.

    A plain search for the forbidden name matches the docstring that
    *explains* why it is forbidden, so a text check would fail this module and
    the rational fix would be to delete the explanation -- leaving the rule
    enforced and unexplained. `api-003` hit exactly this and settled it by
    reading the code as a structure; the same answer applies here.
    """
    # spec: api-006, db-003, api-003
    tree = ast.parse(Path(batch.__file__).read_text(encoding="utf-8"))
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "init_engine" not in referenced | imported
    assert "dispose_engine" not in referenced | imported
    # and the explanation that a text check would have forced out is still here
    assert "init_engine" in (batch.run_batch_now.__doc__ or "")
