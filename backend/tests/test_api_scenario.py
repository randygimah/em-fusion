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

`api-011`'s guard is asserted here rather than in a file of its own, because it
is the same endpoint and reuses every helper below. Two of them changed shape
for it: a launcher now receives the **lease** as well as the request, and
`_post` binds a **fresh guard per call** -- a process-wide singleton shared
between tests would make the second test in this file receive a 409 for the
first test's batch.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Thread
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import NullPool

from alembic import command
from app.api.v1.scenario import get_batch_guard, get_batch_launcher
from app.api.v1.schemas.scenario import BatchRequest
from app.dal.models import ScenarioRunSummary
from app.db.migrations import alembic_config
from app.main import app
from app.pipeline import MAX_RUNS, MIN_RUNS
from app.replay import MANIFEST_NAME
from app.scenario import batch
from app.scenario.guard import (
    BatchAlreadyRunning,
    BatchGuard,
    InFlightBatch,
    Lease,
)
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

    **It does not release the lease by default, and that is the faithful
    default** (`api-011`, second finding). A real launcher returns within
    microseconds and the batch it started runs for about seventy seconds, so
    "called, not finished" is the ordinary state and a stand-in that released at
    once would simulate the one case the guard does not have to handle. Pass
    `release=True` for a batch that has finished.
    """

    def __init__(self, *, release: bool = False) -> None:
        self.calls: list[Any] = []
        self.leases: list[Any] = []
        self._release = release

    def __call__(self, request: Any, lease: Any) -> None:
        self.calls.append(request)
        self.leases.append(lease)
        if self._release:
            lease.release()


class RaisingLauncher:
    """A launcher that cannot even start its thread. Spec: api-011.

    Distinct from a batch that fails *inside* its thread, which the launcher
    logs and the thread's own `finally` releases. This one raises where the
    route can still see it, and the route is what must hand the guard back.
    """

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def __call__(self, request: Any, lease: Any) -> None:
        self.calls.append(request)
        raise RuntimeError("could not start a thread")


@contextmanager
def _bound(guard: BatchGuard, launcher: Any) -> Iterator[TestClient]:
    """A client whose route sees this guard and this launcher.

    Separate from `_post` because the guard's whole subject is what a *second*
    request sees, which needs two requests against one guard.
    """
    app.dependency_overrides[get_batch_launcher] = lambda: launcher
    app.dependency_overrides[get_batch_guard] = lambda: guard
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_batch_launcher, None)
        app.dependency_overrides.pop(get_batch_guard, None)


def _post(body: dict[str, Any]) -> tuple[int, dict[str, Any], RecordingLauncher]:
    launcher = RecordingLauncher()
    with _bound(BatchGuard(), launcher) as client:
        response = client.post("/api/v1/scenario/start", json=body)
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
        batch.launch_batch(_batch_request(), lease=_free_lease())

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


def test_the_launcher_reads_the_seed_from_the_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The container's exact condition, reproduced. Spec: api-006.

    Compose passes the pseudonymisation seed through from the host, so an
    *unset* host variable arrives inside the container as an empty string
    rather than as absent. `load_dotenv(override=False)` treats present-but-
    empty as present, so nothing would shadow a perfectly good `.env`.

    This is the third recurrence of that defect here, and the first two are why
    both command-line entrypoints already clear the variable before reading the
    file. The launcher did not, so every batch started from the screen died on
    a missing seed while the screen reported it accepted.

    Nothing substitutes the pseudonymiser in this test, deliberately: the
    launcher's other tests do, which is exactly why they could not catch this.
    """
    # spec: api-006, adp-007, dal-004
    monkeypatch.setenv("PSEUDONYM_SEED", "")
    (tmp_path / MANIFEST_NAME).write_text("{}")
    env_file = tmp_path / ".env"
    env_file.write_text("PSEUDONYM_SEED=a-seed-from-the-file\n")
    seen: dict[str, Any] = {}

    monkeypatch.setattr(batch, "run_batch", lambda layout, **kw: seen.update(kw))
    monkeypatch.setattr(batch, "available_window", lambda manifest: "window")
    monkeypatch.setattr(batch, "load_layout", lambda: "layout")
    monkeypatch.setattr(batch, "load_exclusions", lambda path: frozenset())
    monkeypatch.setattr(batch, "PostgisObservationRepository", lambda sessions: "repo")
    monkeypatch.setattr(batch, "get_sessionmaker", lambda: "sessions")

    batch.run_batch_now(_batch_request(), data_dir=tmp_path, env_file=env_file)

    assert seen["pseudonymiser"] is not None


def test_a_real_seed_in_the_environment_is_not_shadowed_by_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other half: a seed genuinely set must win. Spec: api-006.

    Without this, clearing the variable could be implemented as clearing it
    always, which would make the file authoritative and silently ignore a seed
    an operator set on purpose.
    """
    # spec: api-006, dal-004
    monkeypatch.setenv("PSEUDONYM_SEED", "the-real-one")
    env_file = tmp_path / ".env"
    env_file.write_text("PSEUDONYM_SEED=the-file-one\n")

    batch.load_seed_environment(env_file)

    assert os.environ["PSEUDONYM_SEED"] == "the-real-one"


# ============================================================ one batch at a
# time
#
# Spec: api-011. The backend was found hung on "QueuePool limit of size 5
# overflow 10 reached, connection timed out", serving nothing, after several
# batches were started from the screen in quick succession. Every start spawns
# another unbounded daemon thread and every thread borrows the API's one engine,
# so batches compete with request serving for a pool whose ceiling is fifteen.
# One batch is harmless -- measured, it adds a single connection while /health
# stays 200 -- so the fault is concurrency, and bounding the count at one
# removes the observed cause.
#
# Two layers, deliberately. The guard is asserted directly, because its whole
# content is what a second caller sees and an HTTP test can only observe that
# through a status code. The route is then asserted through the endpoint,
# because the failure the item is about is a *request* being refused.


def _free_lease() -> Lease:
    """A lease over a guard nothing else holds.

    The launcher's own tests predate the guard and care only that the batch
    ran, so they take one of these rather than growing a guard each.
    """
    return BatchGuard().take(_in_flight())


def _in_flight(*, base_seed: int = 20220627) -> InFlightBatch:
    return InFlightBatch(
        scenario_type=ScenarioType.GNSS_DEGRADATION,
        base_seed=base_seed,
        started_at=datetime(2026, 9, 30, 14, 3, 12, tzinfo=UTC),
    )


# ------------------------------------------------------------------ the guard


def test_nothing_is_in_flight_before_a_batch_is_taken() -> None:
    """The state says so by not existing. Spec: api-011 (second decision)."""
    # spec: api-011
    assert BatchGuard().in_flight is None


def test_the_guard_admits_one_batch() -> None:
    """A start arriving when nothing is running behaves as api-006 describes."""
    # spec: api-011, api-006
    guard = BatchGuard()

    lease = guard.take(_in_flight())

    assert lease is not None
    assert guard.in_flight == _in_flight()


def test_the_guard_refuses_a_second_batch() -> None:
    """The whole item, at the layer that decides it."""
    # spec: api-011
    guard = BatchGuard()
    guard.take(_in_flight())

    with pytest.raises(BatchAlreadyRunning):
        guard.take(_in_flight(base_seed=999))


def test_the_refusal_carries_what_is_already_running() -> None:
    """Atomically, and that is the reason it is on the exception.

    Returning a bare "no" and making the caller ask `in_flight` afterwards is a
    race: the running batch can finish in between, leaving a 409 with nothing to
    name. Spec: api-011 (sixth decision).
    """
    # spec: api-011
    guard = BatchGuard()
    guard.take(_in_flight())

    with pytest.raises(BatchAlreadyRunning) as refusal:
        guard.take(_in_flight(base_seed=999))

    assert refusal.value.in_flight == _in_flight()


def test_releasing_the_lease_admits_the_next_batch() -> None:
    """Spec: api-011 (fourth decision)."""
    # spec: api-011
    guard = BatchGuard()
    lease = guard.take(_in_flight())

    lease.release()

    assert guard.in_flight is None
    assert guard.take(_in_flight(base_seed=999)) is not None


def test_a_stale_lease_does_not_release_a_later_batch() -> None:
    """The hazard that makes release idempotence the wrong answer.

    A release that simply clears the guard would let a lease from a finished
    batch free the guard a *later* batch is holding, and then two batches run at
    once -- the item defeating itself by the mechanism meant to enforce it. So a
    lease releases only while it is still the holder.
    """
    # spec: api-011
    guard = BatchGuard()
    first = guard.take(_in_flight())
    first.release()
    second = guard.take(_in_flight(base_seed=999))

    first.release()

    assert guard.in_flight == _in_flight(base_seed=999)
    with pytest.raises(BatchAlreadyRunning):
        guard.take(_in_flight(base_seed=555))
    second.release()


def test_taking_the_guard_is_atomic() -> None:
    """Spec: api-011 (fifth decision).

    A check followed by a set lets two simultaneous callers both observe
    "nothing running" and both proceed, which defeats the item entirely while
    passing every test that takes the guard twice in a row. The barrier is what
    makes the interleaving certain rather than hoped for: both threads are
    inside `take` at the same moment or the test times out.
    """
    # spec: api-011
    guard = BatchGuard()
    gate = Barrier(2, timeout=5)
    taken: list[Lease] = []
    refused: list[BatchAlreadyRunning] = []

    def contend(seed: int) -> None:
        gate.wait()
        try:
            taken.append(guard.take(_in_flight(base_seed=seed)))
        except BatchAlreadyRunning as refusal:
            refused.append(refusal)

    threads = [Thread(target=contend, args=(seed,)) for seed in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(taken) == 1
    assert len(refused) == 1


def test_the_guard_writes_nothing_to_the_database() -> None:
    """Spec: api-011 (second decision), db-007.

    A persisted "running" flag would be a claim no crash could retract: kill the
    container mid-batch and the row still says a batch is in flight, locking the
    button until somebody edits the database. `db-007` rejected exactly this
    when it refused a three-valued status column. Asserted against the parsed
    imports rather than the text, on `api-003`'s reasoning -- a text search would
    match the docstring explaining the rule.
    """
    # spec: api-011, db-007, api-003
    from app.scenario import guard as guard_module

    tree = ast.parse(Path(guard_module.__file__).read_text(encoding="utf-8"))
    reached = {
        module
        for node in ast.walk(tree)
        for module in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        )
    }

    assert not any(
        module.startswith(("app.db", "sqlalchemy", "alembic")) for module in reached
    ), f"the guard reaches storage: {sorted(reached)}"


# ------------------------------------------------------------------ the route


def test_a_second_start_while_one_runs_is_refused() -> None:
    """Spec: api-011. The refusal an analyst actually meets."""
    # spec: api-011
    launcher = RecordingLauncher()
    with _bound(BatchGuard(), launcher) as client:
        first = client.post("/api/v1/scenario/start", json=CONFIGURATION)
        second = client.post("/api/v1/scenario/start", json=CONFIGURATION)

    assert first.status_code == 202
    assert second.status_code == 409


def test_a_refused_second_start_starts_no_second_batch() -> None:
    """No second batch, no run rows, no second thread. Spec: api-011."""
    # spec: api-011
    launcher = RecordingLauncher()
    with _bound(BatchGuard(), launcher) as client:
        client.post("/api/v1/scenario/start", json=CONFIGURATION)
        client.post("/api/v1/scenario/start", json=CONFIGURATION)

    assert len(launcher.calls) == 1


def test_the_refusal_names_the_batch_already_running() -> None:
    """Spec: api-011 (sixth decision), fourth finding.

    An analyst who cannot tell which batch is in flight, or how long it has
    been, cannot tell whether to wait or to investigate -- and the information
    costs nothing, the guard holding it in order to exist.

    The key set is asserted **exactly**, which is what keeps api-009 mechanical:
    a field added here later has to be argued for in this test rather than
    arriving with the injected event in tow.
    """
    # spec: api-011, api-009
    launcher = RecordingLauncher()
    with _bound(BatchGuard(), launcher) as client:
        client.post("/api/v1/scenario/start", json=CONFIGURATION)
        refusal = client.post("/api/v1/scenario/start", json=CONFIGURATION)

    detail = refusal.json()["detail"]
    assert set(detail) == {"scenarioType", "baseSeed", "startedAt"}
    assert detail["scenarioType"] == "gnss-degradation"
    assert detail["baseSeed"] == 20220627
    assert datetime.fromisoformat(detail["startedAt"]).tzinfo is not None


def test_the_refusal_carries_no_answer_key() -> None:
    """Spec: api-009. The injected event is not among what a 409 reports."""
    # spec: api-011, api-009
    launcher = RecordingLauncher()
    with _bound(BatchGuard(), launcher) as client:
        client.post("/api/v1/scenario/start", json=CONFIGURATION)
        refusal = client.post("/api/v1/scenario/start", json=CONFIGURATION)

    body = refusal.text
    for leak in ("incident", "radius", "elevation", "groundTruth", "ground_truth"):
        assert leak not in body


def test_a_start_after_the_batch_finished_is_accepted() -> None:
    """The guard is a bound on concurrency, not a bound on batches."""
    # spec: api-011
    launcher = RecordingLauncher(release=True)
    with _bound(BatchGuard(), launcher) as client:
        first = client.post("/api/v1/scenario/start", json=CONFIGURATION)
        second = client.post("/api/v1/scenario/start", json=CONFIGURATION)

    assert (first.status_code, second.status_code) == (202, 202)
    assert len(launcher.calls) == 2


def test_the_route_hands_the_lease_to_the_launcher() -> None:
    """Spec: api-011, second finding.

    The launcher returns within microseconds and the batch runs for about
    seventy seconds, so the release belongs to the thread -- which means the
    lease has to cross the seam rather than being held here.
    """
    # spec: api-011, api-006
    launcher = RecordingLauncher()
    with _bound(BatchGuard(), launcher) as client:
        client.post("/api/v1/scenario/start", json=CONFIGURATION)

    assert len(launcher.leases) == 1
    assert hasattr(launcher.leases[0], "release")


def test_a_launcher_that_raises_frees_the_guard() -> None:
    """The item's sharpest failure case. Spec: api-011 (fourth decision).

    One failure disabling the button until the container is restarted would
    convert a recoverable error into an outage -- a worse defect than the one
    this item fixes.
    """
    # spec: api-011
    guard = BatchGuard()
    with _bound(guard, RaisingLauncher()) as client:
        with pytest.raises(RuntimeError):
            client.post("/api/v1/scenario/start", json=CONFIGURATION)

    assert guard.in_flight is None

    launcher = RecordingLauncher()
    with _bound(guard, launcher) as client:
        after = client.post("/api/v1/scenario/start", json=CONFIGURATION)

    assert after.status_code == 202
    assert len(launcher.calls) == 1


@pytest.mark.parametrize(
    "invalid",
    [
        {"scenarioType": "sixth-type"},
        {"runs": MIN_RUNS - 1},
        {"incidentOffsetS": 900},
    ],
)
def test_a_refused_configuration_does_not_consume_the_guard(
    invalid: dict[str, Any],
) -> None:
    """Spec: api-011, third finding.

    The guard is taken in the handler body and never in a dependency, because a
    dependency is resolved whether or not the body validates. Taken there, a 422
    would consume it and the next valid start would be refused 409 with nothing
    running at all.
    """
    # spec: api-011, api-006
    guard = BatchGuard()
    launcher = RecordingLauncher()
    with _bound(guard, launcher) as client:
        refused = client.post(
            "/api/v1/scenario/start", json={**CONFIGURATION, **invalid}
        )
        accepted = client.post("/api/v1/scenario/start", json=CONFIGURATION)

    assert refused.status_code == 422
    assert accepted.status_code == 202
    assert len(launcher.calls) == 1


def test_two_simultaneous_starts_give_one_acceptance_and_one_refusal() -> None:
    """Spec: api-011 (fifth decision), at the layer that answers a request.

    The barrier sits inside the guard so both handlers are provably inside
    `take` together. It also means the test cannot pass for the wrong reason: if
    the requests were serialised the barrier would time out rather than quietly
    assert two sequential starts.
    """
    # spec: api-011
    gate = Barrier(2, timeout=5)

    class _BarrierGuard(BatchGuard):
        def take(self, in_flight: InFlightBatch) -> Lease:
            gate.wait()
            return super().take(in_flight)

    statuses: list[int] = []
    launcher = RecordingLauncher()
    with _bound(_BarrierGuard(), launcher) as client:

        def start() -> None:
            statuses.append(
                client.post("/api/v1/scenario/start", json=CONFIGURATION).status_code
            )

        threads = [Thread(target=start) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

    assert sorted(statuses) == [202, 409]
    assert len(launcher.calls) == 1


# ---------------------------------------------------------------- the launcher
# side of the lease


def test_the_launcher_releases_the_lease_when_the_batch_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec: api-011 (fourth decision)."""
    # spec: api-011
    guard = BatchGuard()
    lease = guard.take(_in_flight())
    monkeypatch.setattr(batch, "Thread", _InlineThread)
    monkeypatch.setattr(batch, "run_batch_now", lambda request: None)

    batch.launch_batch(_batch_request(), lease=lease)

    assert guard.in_flight is None


def test_the_launcher_releases_the_lease_when_the_batch_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Released in a `finally`, always. Spec: api-011 (fourth decision).

    A batch that raises must free it. This is the same failure the launcher
    already logs rather than raises; what is new is that the guard comes back.
    """
    # spec: api-011, api-006

    def explode(request: Any) -> None:
        raise RuntimeError("no corpus on disk")

    guard = BatchGuard()
    lease = guard.take(_in_flight())
    monkeypatch.setattr(batch, "Thread", _InlineThread)
    monkeypatch.setattr(batch, "run_batch_now", explode)

    with caplog.at_level("ERROR"):
        batch.launch_batch(_batch_request(), lease=lease)

    assert "scenario batch failed" in caplog.text
    assert guard.in_flight is None


# ------------------------------------------------- the condition the guard needs


DOCKERFILE_PATHS = (
    Path(__file__).resolve().parents[1] / "Dockerfile",
    Path("/app/Dockerfile"),
)
API_COMPOSE_PATHS = (
    Path(__file__).resolve().parents[2] / "compose.yaml",
    Path("/repo/compose.yaml"),
)


def _read_one(candidates: tuple[Path, ...]) -> str:
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise AssertionError(  # pragma: no cover -- a broken checkout or mount
        f"not found at any of {[str(p) for p in candidates]}; skipping is not "
        "an option, since a skipped structural test passes for the wrong reason."
    )


def _uvicorn_invocations() -> list[str]:
    """Every place this repository starts the API, comments removed.

    Three of them: the Dockerfile's development and production stages, and the
    compose command that overrides both.
    """
    lines = [
        line
        for source in (_read_one(DOCKERFILE_PATHS), _read_one(API_COMPOSE_PATHS))
        for line in source.splitlines()
        if not line.strip().startswith("#") and "uvicorn" in line
    ]
    return [line for line in lines if "app.main:app" in line]


def test_every_way_of_starting_the_api_is_found() -> None:
    """The guard's assertion is worth nothing if it reads no invocation.

    A pattern that matched none of them would make the test below pass by
    finding nothing to object to, which is the failure mode of every structural
    check in this repository.
    """
    # spec: api-011 (third decision), sixth finding
    assert len(_uvicorn_invocations()) == 3


@pytest.mark.parametrize("invocation", _uvicorn_invocations())
def test_the_api_runs_as_a_single_worker(invocation: str) -> None:
    """Spec: api-011 (third decision), sixth finding.

    In-process state is sound only while the API is one process. Adding workers
    would give each its own guard and silently restore the defect, so the guard
    and the condition it depends on are asserted together -- the guard alone
    would keep passing while becoming untrue.
    """
    # spec: api-011
    assert "--workers" not in invocation


# ------------------------------------------------- the seam's shipped defaults
#
# Every test above substitutes both dependencies, which is what makes the
# refusals assertable without a corpus -- and it means nothing above asserts what
# the *application* gets. Both failures are silent: a launcher returning a no-op
# would leave the screen answering 202 and running nothing, and a guard built
# fresh per call would give every request its own, making the bound vacuous while
# every test with an override still passed.


def test_the_shipped_launcher_is_the_one_that_runs_a_batch() -> None:
    # spec: api-006
    assert get_batch_launcher() is batch.launch_batch


def test_the_shipped_guard_is_the_one_the_process_shares() -> None:
    """Spec: api-011 (second and third decisions).

    One guard per process, which is the whole scope of the state. A factory
    handing out a new guard each call would bound nothing at all.
    """
    # spec: api-011
    from app.scenario.guard import BATCH_GUARD

    assert get_batch_guard() is BATCH_GUARD
    assert get_batch_guard() is get_batch_guard()
