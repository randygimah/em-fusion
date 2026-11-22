"""The answer key never reaches the detectors or the analyst. Spec: api-009.

Every detection figure in the thesis is computed against an answer key the
generator writes when it stages an incident. If a detector could read that
key, or an analyst could see it, the figures would measure reading rather
than detecting. Until this file the claim rested on separate guarantees --
a run record with no field for the key, the bundle and model-payload tests,
`api-012`'s heading fix -- and `api-012` found the scenario type in a
heading that every one of those had passed. So it is proved here once,
across the whole surface, in two ways.

**Statically, over the code that must not look.** Parsed, not grepped, for
the reason `db-006` records: a substring search is satisfied by a docstring
that explains the rule. A *read* is an attribute or a subscript named
`scenario_type`, `scenarioType` or `ground_truth`, or a non-docstring string
literal naming the column. Declaring a field of that name is not a read.

**Live, over every response an analyst's screen receives**, for a run of
each of the five scenario types whose answer key holds canary values.

**One declared exception.** Scenario Control is the experimenter's console:
the operator picks the scenario type to start a batch, so its router and
schema carry the type and the screen shows it. They never carry the key's
content, which the last test proves.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.main import app
from app.scenario.incident import ScenarioType
from tests.conftest import RUN_ID, START, requires_database
from tests.test_api_hypotheses import screen  # noqa: F401 -- a fixture
from tests.test_db_hypotheses import OTHER_RUN_ID, neighbours  # noqa: F401

APP = Path(__file__).resolve().parents[1] / "app"

#: The layers that must never look at what a run staged.
GUARDED = ("detection", "ai", "dal", "adapters", "api")

#: The console, and nothing else. Each entry must still contain a read, so a
#: stale exception fails rather than quietly widening the rule.
CONSOLE = frozenset({"api/v1/scenario.py", "api/v1/schemas/scenario.py"})

#: Where the answer-key column may be named at all: the module that builds the
#: key, the pipeline that records it, and the repository that writes it. The
#: harness reads it from outside `app/`, in the measurement scripts.
KEY_WRITERS = frozenset({"scenario/incident.py", "pipeline.py", "db/repository.py"})

NAMES = frozenset({"scenario_type", "scenarioType", "ground_truth"})
COLUMN = re.compile(r"\b(scenario_type|ground_truth)\b")

#: Field names only the answer key uses. Generic words in it (`window`,
#: `sensors`, `seed`) appear legitimately in responses and are covered by the
#: canary values instead.
KEY_FIELDS = (
    "ground_truth",
    "spectral_extent",
    "elevation_db",
    "track_mode",
    "aircraft_eligible",
    "aircraft_requested",
    "aircraft_floor_reached",
)
CANARY = "CANARY-7f3e"


# ----------------------------------------------------------------- the scanner


def _docstrings(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def reads(source: str) -> list[str]:
    """Every place this source reads a run's type or answer key."""
    tree = ast.parse(source)
    skip = _docstrings(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in NAMES:
            found.append(f"line {node.lineno}: .{node.attr}")
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and node.slice.value in NAMES
        ):
            found.append(f"line {node.lineno}: [{node.slice.value!r}]")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
            and COLUMN.search(node.value)
        ):
            names = sorted(set(COLUMN.findall(node.value)))
            found.append(f"line {node.lineno}: string naming {', '.join(names)}")
    return found


def _modules(*roots: str) -> list[Path]:
    return sorted(p for root in roots for p in (APP / root).rglob("*.py"))


def _rel(path: Path) -> str:
    return path.relative_to(APP).as_posix()


# spec: api-009 -- the scanner itself, against synthetic sources


def test_the_scanner_finds_an_attribute_read() -> None:
    assert reads("def f(run):\n    return run.scenario_type\n")


def test_the_scanner_finds_a_subscript_read() -> None:
    assert reads("def f(row):\n    return row['ground_truth']\n")


def test_the_scanner_finds_the_column_in_sql() -> None:
    assert reads("Q = 'SELECT ground_truth FROM scenario_runs'\n")


def test_the_scanner_ignores_a_docstring_explaining_the_rule() -> None:
    source = (
        '"""Never read scenario_type or ground_truth here."""\n\n'
        'def f():\n    """Nor ground_truth."""\n'
    )
    assert reads(source) == []


def test_the_scanner_ignores_a_field_declaration() -> None:
    assert reads("class Run:\n    scenario_type: str\n") == []


# spec: api-009 -- the layers that must not look


@pytest.mark.parametrize("path", _modules(*GUARDED), ids=_rel)
def test_no_guarded_module_reads_a_runs_type_or_answer_key(path: Path) -> None:
    if _rel(path) in CONSOLE:
        pytest.skip("the experimenter's console, declared")
    assert reads(path.read_text()) == [], _rel(path)


@pytest.mark.parametrize("name", sorted(CONSOLE))
def test_each_declared_exception_still_needs_to_be_one(name: str) -> None:
    assert reads((APP / name).read_text()), f"{name} no longer reads the type"


def test_the_answer_key_column_is_named_only_where_it_is_written() -> None:
    naming = {
        _rel(path)
        for path in _modules(".")
        if any("ground_truth" in hit for hit in reads(path.read_text()))
    }
    assert naming <= KEY_WRITERS, sorted(naming - KEY_WRITERS)


# ------------------------------------------------------------ live, every route


def _answer_key(scenario_type: str) -> dict[str, object]:
    """The real key's shape, every value a canary that must never be served."""
    return {
        "scenario_type": scenario_type,
        "seed": 990013,
        "spectral_extent": f"{CANARY}-extent",
        "sensors": [f"{CANARY}-sensor"],
        "channels": [99],
        "elevation_db": 77.7,
        "window": {"start": f"{CANARY}-start", "end": f"{CANARY}-end"},
        "track_mode": f"{CANARY}-mode",
        "aircraft": [f"{CANARY}-aircraft"],
        "aircraft_eligible": 913,
        "aircraft_requested": 917,
        "aircraft_floor_reached": True,
    }


def _stage(engine: Engine, scenario_type: str) -> None:
    with engine.connect() as connection:
        for run in (RUN_ID, OTHER_RUN_ID):
            connection.execute(
                text(
                    "UPDATE scenario_runs SET scenario_type = :type, "
                    "ground_truth = CAST(:key AS jsonb), "
                    "parameters = CAST(:parameters AS jsonb), "
                    "completed_at = now(), detection_pass_at = now(), "
                    "detection_policy = CAST(:policy AS jsonb) WHERE id = :id"
                ),
                {
                    "id": run,
                    "type": scenario_type,
                    "key": json.dumps(_answer_key(scenario_type)),
                    "parameters": json.dumps(
                        {"start": START.isoformat(), "duration_seconds": 900}
                    ),
                    "policy": json.dumps({"RF-NOISE.threshold_db": "6.0"}),
                },
            )
        connection.commit()


def _analyst_responses(client: TestClient) -> dict[str, str]:
    base = "/api/v1/operational-picture"
    window = "from=2022-06-27T12:00:00Z&to=2022-06-27T12:05:00Z"
    paths = [
        f"{base}?run={RUN_ID}",
        f"{base}?run={RUN_ID}&view=all",
        f"{base}/hours",
        f"{base}/evidence?run={RUN_ID}",
        f"{base}/tracks?run={RUN_ID}&{window}",
        f"{base}/receiver-states?run={RUN_ID}",
        "/api/v1/hypotheses",
    ]
    served = {path: client.get(path) for path in paths}
    listing = served["/api/v1/hypotheses"].json()
    for entry in listing["hypotheses"]:
        path = f"/api/v1/hypotheses/{entry['id']}"
        served[path] = client.get(path)
    for path, response in served.items():
        assert response.status_code == 200, (path, response.status_code, response.text)
    return {path: response.text for path, response in served.items()}


@pytest.mark.database
@requires_database
@pytest.mark.parametrize("scenario_type", [t.value for t in ScenarioType])
def test_no_analyst_route_serves_the_type_or_the_key(
    scenario_type: str,
    migrated_database: Engine,
    screen: dict[str, int],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage(migrated_database, scenario_type)
    monkeypatch.setenv(
        "DATABASE_URL", migrated_database.url.render_as_string(hide_password=False)
    )
    with TestClient(app) as client:
        served = _analyst_responses(client)

    assert len(served) >= 9, sorted(served)  # seven routes and at least two details
    forbidden = (*(t.value for t in ScenarioType), *KEY_FIELDS, CANARY)
    leaks = {
        path: [word for word in forbidden if word in body]
        for path, body in served.items()
        if any(word in body for word in forbidden)
    }
    assert leaks == {}


@pytest.mark.database
@requires_database
def test_the_console_shows_the_type_and_never_the_key(
    migrated_database: Engine,
    screen: dict[str, int],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage(migrated_database, ScenarioType.GNSS_DEGRADATION.value)
    monkeypatch.setenv(
        "DATABASE_URL", migrated_database.url.render_as_string(hide_password=False)
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/scenario/runs")
    assert response.status_code == 200
    assert ScenarioType.GNSS_DEGRADATION.value in response.text
    assert CANARY not in response.text
    assert not any(field in response.text for field in KEY_FIELDS)
