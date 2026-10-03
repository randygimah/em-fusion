"""The picture serves a named hour, and the index of hours it will serve.

Spec: `api-013`.

Four kinds of test, following `api-002`'s own split.

**Contract parity** for the new shape, which rides the existing machinery
rather than a second copy of it: `SelectableHour` is declared in
`operationalPicture.ts` alongside the picture's other interfaces, so
`test_api_operational_picture.py`'s parser check -- every interface in the
contract has a model, and the field sets match in both directions -- covers it
the moment it exists. What is here instead is the half that parity cannot see:
which fields the shape must *not* have.

**Two absences, and they are different claims.** The index must carry no
scenario type, which is `api-009`; and it must carry nothing the detectors
concluded, which is not `api-009` at all -- a detector's conclusion is what an
analyst is meant to see, and is served in full for the hour actually selected.
It is kept out of the *chooser* because on this corpus precision is 1.000 and
recall is 60 of 60 on every positive arm, so a count of reportable findings is
empirically a near-perfect proxy for whether anything was staged, and an hour
chooser ranked by it would make any later exercise in which a person reads this
screen un-blind with nothing in the code saying so.

Both are asserted **structurally** -- over the field set, so the shape cannot
express the leak -- and the first is asserted again over the serialised payload
across all five arms, because `api-012` learned that a check on one field only
ever proves the field somebody thought of. The serialisation check is paired
with an interlock firing it at the harness listing, which carries the scenario
type legitimately: a scan that cannot find a real leak is not a scan.

**The endpoint against a live database**, marked and skipped without one. The
refusal of an unknown run is the sharpest case in the item: silently serving a
different hour from the one asked for is indistinguishable from the feature
working.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.schemas.operational_picture import (
    OperationalPicture,
    SelectableHour,
)
from app.api.v1.schemas.scenario import ScenarioRunListing
from app.dal.models import SelectableRun
from app.db.repository import HOURS_LIMIT, selectable_hours
from app.main import app
from app.scenario.incident import ScenarioType
from tests.conftest import requires_database
from tests.contracts import contract_paths
from tests.contracts import interfaces as _interfaces
from tests.contracts import read_contract as _read

CONTRACT_PATHS = contract_paths("operationalPicture.ts")

HOURS_PATH = "/api/v1/operational-picture/hours"
PICTURE_PATH = "/api/v1/operational-picture"

#: The replayed hour the corpus windows are cut from, in simulated time. Not
#: the wall clock: a run row's `started_at` is when the generator ran, and
#: labelling a 2022 hour of air traffic with it is `anom-009`'s recorded
#: mistake wearing a different hat.
OBSERVED_FROM = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
DURATION_S = 900

#: When the generator ran, which must never reach the window fields.
GENERATED_AT = datetime(2026, 10, 3, 11, 18, 0, tzinfo=UTC)

#: Every field the index is allowed to carry, asserted exactly. A new field
#: has to be argued for here, which is the point: the shapes this item refuses
#: are refused by not existing, and a set compared by `<=` would admit them.
ALLOWED_FIELDS = {"runId", "observedFrom", "observedTo", "examined"}

#: The same four at the repository boundary, in that layer's own vocabulary.
#: **Asserted here as well, because the mutation pass showed it was not.** Two
#: mutants adding a field to `SelectableRun` -- the scenario type, and a finding
#: count -- both survived: every assertion in this file was about the shape that
#: is *served*, and `SelectableHour.of` names its four fields explicitly, so
#: neither mutant reached the wire. That makes them harmless and the gap real.
#: The claim this item rests on is that the guarantee is **structural** -- a
#: shape with no field for the answer cannot leak it -- and it was structural at
#: one boundary and nowhere else, while the layer below is exactly where somebody
#: would add the field, in the query, to make the chooser more useful. One more
#: edit in `of` and it is on the screen.
ALLOWED_REPOSITORY_FIELDS = {"run_id", "observed_from", "observed_to", "examined"}

#: Words that would mean a conclusion had reached the chooser. Matched against
#: field names rather than against values, because the field is what makes the
#: value available at all.
CONCLUSION_WORDS = (
    "finding",
    "anomaly",
    "severity",
    "claim",
    "level",
    "count",
    "interesting",
    "detected",
    "zone",
    "fault",
)

ARMS = tuple(member.value for member in ScenarioType)


# ------------------------------------------------------------------- helpers


def _fields(model: Any) -> set[str]:
    return set(model.model_json_schema(by_alias=True)["properties"])


def _insert_run(
    engine: Engine,
    run_id: int,
    *,
    completed: bool = True,
    scenario_type: str = "normal-baseline",
    generated_offset_s: int = 0,
    observed_offset_s: int = 0,
    window: bool = True,
    examined: bool = False,
) -> None:
    """One run row, with the two clocks kept deliberately far apart."""
    parameters: dict[str, Any] = {}
    if window:
        parameters = {
            "start": (OBSERVED_FROM + timedelta(seconds=observed_offset_s)).isoformat(),
            "duration_seconds": DURATION_S,
        }
    started = GENERATED_AT + timedelta(seconds=generated_offset_s)
    with engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs (id, scenario_type, parameters, seed, "
                "started_at, completed_at, detection_pass_at, detection_policy) "
                "VALUES (:id, :type, CAST(:parameters AS jsonb), 0, :started, "
                ":completed, :examined, :policy)"
            ),
            {
                "id": run_id,
                "type": scenario_type,
                "parameters": json.dumps(parameters),
                "started": started,
                "completed": started + timedelta(seconds=40) if completed else None,
                "examined": started + timedelta(seconds=60) if examined else None,
                "policy": json.dumps({"rf": {"threshold": 6.0}}) if examined else None,
            },
        )
        connection.commit()


def _client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    return TestClient(app)


def _hours(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    with _client(engine, monkeypatch) as client:
        response = client.get(HOURS_PATH)
    assert response.status_code == 200, response.text
    return list(response.json())


# ------------------------------------------------------- what the shape refuses


def test_the_index_entry_declares_exactly_the_four_fields() -> None:
    """Spec: api-013.

    Exact equality rather than a subset. Every constraint in this item is a
    statement about what the shape cannot express, and a subset assertion lets
    a thirteenth field arrive without anybody arguing for it.
    """
    # spec: api-013
    assert _fields(SelectableHour) == ALLOWED_FIELDS


def test_the_index_entry_has_no_field_for_the_scenario_type() -> None:
    """`api-009`, structurally rather than by discipline.

    The same argument `ScenarioRunSummary` was built on: a shape with no field
    for the answer cannot leak it on any run, which is stronger than
    remembering to strip it per endpoint.
    """
    # spec: api-013, api-009
    declared = " ".join(_fields(SelectableHour)).lower()

    assert "scenario" not in declared
    assert "type" not in declared
    assert "seed" not in declared
    assert "parameter" not in declared


def test_the_repository_row_declares_exactly_the_four_fields() -> None:
    """Spec: api-013 -- the gap the mutation pass found.

    `SelectableRun` is what the query returns and `SelectableHour` is what is
    served. Both are asserted, because "the shape cannot express it" is only a
    structural guarantee at the boundaries where something checks the shape.
    """
    # spec: api-013, api-009
    assert _fields(SelectableRun) == ALLOWED_REPOSITORY_FIELDS


@pytest.mark.parametrize("word", ("scenario", "type", "seed", *CONCLUSION_WORDS))
def test_the_repository_row_carries_neither_the_answer_nor_a_conclusion(
    word: str,
) -> None:
    # spec: api-013, api-009 -- the same two absences one layer down, where a
    # field would be added first because that is where the query is written
    assert not any(word in field.lower() for field in _fields(SelectableRun))


@pytest.mark.parametrize("word", CONCLUSION_WORDS)
def test_the_index_entry_carries_nothing_the_detectors_concluded(word: str) -> None:
    """Spec: api-013 -- the second absence, and it is not `api-009`.

    A detector's conclusion is what an analyst is meant to see and is served in
    full for the hour selected. It is kept out of the chooser because on this
    corpus it coincides with the answer key, so ranking hours by it would
    un-blind any later exercise in which a person reads this screen.
    """
    # spec: api-013, eval-006
    assert not any(word in field.lower() for field in _fields(SelectableHour))


def test_the_index_entry_is_not_the_harness_listing() -> None:
    """Spec: api-013 -- the deliberate difference, recorded as an assertion.

    `/api/v1/scenario/runs` already serves the list a selector wants, and
    carries the scenario type legitimately: Scenario Control is the harness's
    own face. This endpoint exists because that same string is disqualifying on
    the analyst's screen, so the two shapes are asserted to differ on exactly
    that field rather than left to look like an oversight.
    """
    # spec: api-013, api-009
    assert "scenarioType" in _fields(ScenarioRunListing)
    assert "scenarioType" not in _fields(SelectableHour)


def test_the_window_is_nullable_on_both_sides_of_the_contract() -> None:
    """Spec: api-013, amendment (a).

    A replay run records no simulated window, so an hour that cannot name
    itself says so. The alternative -- filling it from `started_at` -- is the
    failure case: that is the wall-clock minute the generator ran.
    """
    # spec: api-013, anom-009
    declared = _interfaces(_read(CONTRACT_PATHS))["SelectableHour"]
    schema = SelectableHour.model_json_schema(by_alias=True)["properties"]

    for field in ("observedFrom", "observedTo"):
        assert "null" in declared[field]
        assert "null" in str(schema[field]).lower()


# -------------------------------------------------- the index, live


@pytest.fixture
def hours_database(migrated_database: Engine) -> Engine:
    """Head, with the single seeded run removed: each test states its own."""
    with migrated_database.connect() as connection:
        connection.execute(text("DELETE FROM observations"))
        connection.execute(text("DELETE FROM scenario_runs"))
        connection.commit()
    return migrated_database


@pytest.mark.database
@requires_database
def test_an_empty_store_serves_an_empty_index_rather_than_a_refusal(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-013 -- amendment (c), on api-002's own argument: a screen that
    # cannot render before the first run is a screen nobody can develop against
    assert _hours(hours_database, monkeypatch) == []


@pytest.mark.database
@requires_database
def test_the_index_serves_only_the_four_fields_it_declares(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-013 -- the shape assertion again over the wire, because a route
    # is free to serve a dict rather than the model it annotates
    _insert_run(hours_database, 1)

    assert set(_hours(hours_database, monkeypatch)[0]) == ALLOWED_FIELDS


@pytest.mark.database
@requires_database
def test_the_index_lists_only_runs_known_to_have_completed(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: api-013, db-007.

    A run that died holds part of an hour. The index is the set of whole hours
    worth offering a person; the run parameter still reaches the other one,
    which is the asymmetry this item states rather than hides.
    """
    # spec: api-013, db-007
    _insert_run(hours_database, 1, completed=True)
    _insert_run(hours_database, 2, completed=False)

    assert [entry["runId"] for entry in _hours(hours_database, monkeypatch)] == [1]


@pytest.mark.database
@requires_database
def test_the_index_is_ordered_newest_first(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-013 -- an unordered index takes its order from the heap, which
    # this repository has had to correct three times
    _insert_run(hours_database, 1, generated_offset_s=0)
    _insert_run(hours_database, 2, generated_offset_s=120)
    _insert_run(hours_database, 3, generated_offset_s=60)

    assert [entry["runId"] for entry in _hours(hours_database, monkeypatch)] == [
        2,
        3,
        1,
    ]


@pytest.mark.database
@requires_database
def test_the_window_is_the_replayed_hour_and_not_the_wall_clock(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: api-013 -- the named failure case of amendment (a).

    The two clocks are four years apart in the fixture on purpose, so an
    implementation reaching for the nearest timestamp is caught by the year
    rather than by a subtlety.
    """
    # spec: api-013, anom-009
    _insert_run(hours_database, 1, observed_offset_s=0)

    entry = _hours(hours_database, monkeypatch)[0]

    assert entry["observedFrom"] is not None
    assert datetime.fromisoformat(entry["observedFrom"]) == OBSERVED_FROM
    assert datetime.fromisoformat(entry["observedTo"]) == OBSERVED_FROM + timedelta(
        seconds=DURATION_S
    )
    assert str(GENERATED_AT.year) not in json.dumps(entry)


@pytest.mark.database
@requires_database
def test_a_run_recording_no_window_carries_none_rather_than_a_substitute(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-013 -- a replay run records no simulated window, and an hour
    # that cannot name itself says so rather than borrowing the generator's clock
    _insert_run(hours_database, 1, window=False)

    entry = _hours(hours_database, monkeypatch)[0]

    assert entry["runId"] == 1
    assert entry["observedFrom"] is None
    assert entry["observedTo"] is None


@pytest.mark.database
@requires_database
def test_the_index_says_whether_an_hour_was_examined(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: api-013, api-012.

    The one thing the chooser does say about an hour, and it is a different
    kind of fact from what was found: whether anybody looked is answered by the
    presence of the account and never by a number in it.
    """
    # spec: api-013, api-012, anom-015
    _insert_run(hours_database, 1, examined=False)
    _insert_run(hours_database, 2, examined=True, generated_offset_s=60)

    examined = {
        entry["runId"]: entry["examined"]
        for entry in _hours(hours_database, monkeypatch)
    }

    assert examined == {1: False, 2: True}


@pytest.mark.database
@requires_database
def test_the_index_is_bounded(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: api-013, amendment (b).

    The bound exists as a ceiling rather than as a trim: a bound of 50 would
    list hours 371-420 of a 400-hour store and therefore almost none of the 240
    that hold a claim, which is the entire thing this item exists to reach.
    """
    # spec: api-013
    for run_id in range(1, 6):
        _insert_run(hours_database, run_id, generated_offset_s=run_id)

    assert HOURS_LIMIT >= 400
    assert len(selectable_hours(sessionmaker(bind=hours_database), limit=3)) == 3


@pytest.mark.database
@requires_database
@pytest.mark.parametrize("arm", ARMS)
def test_no_field_anywhere_in_the_index_carries_the_scenario_type(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch, arm: str
) -> None:
    """Spec: api-013, api-009.

    Over the **serialised payload** and over all five arms, following
    `api-012`: the failure case says "as a field, a label, or anything from
    which it can be inferred", and a per-field check only ever proves the field
    somebody thought of.
    """
    # spec: api-013, api-009
    for index, scenario_type in enumerate(ARMS):
        _insert_run(
            hours_database,
            index + 1,
            scenario_type=scenario_type,
            generated_offset_s=index,
        )

    assert arm not in json.dumps(_hours(hours_database, monkeypatch))


@pytest.mark.database
@requires_database
def test_the_scan_finds_a_real_leak_when_it_is_there(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The interlock. Spec: api-013.

    The scan above passes on an endpoint that serves nothing at all, so it is
    fired at the harness listing -- which carries the scenario type on purpose
    -- and required to find it. A guard verified only against the case it must
    pass is verified against the author's model of the world.
    """
    # spec: api-013, api-009
    _insert_run(hours_database, 1, scenario_type="gnss-degradation")

    with _client(hours_database, monkeypatch) as client:
        listing = client.get("/api/v1/scenario/runs")

    assert listing.status_code == 200
    assert "gnss-degradation" in json.dumps(listing.json())


# ------------------------------------------------ the picture, for a named hour


@pytest.mark.database
@requires_database
def test_the_picture_serves_the_run_it_was_asked_for(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-013 -- the capability itself
    _insert_run(hours_database, 1, generated_offset_s=0)
    _insert_run(hours_database, 2, generated_offset_s=600)

    with _client(hours_database, monkeypatch) as client:
        response = client.get(PICTURE_PATH, params={"run": 1})

    assert response.status_code == 200
    assert response.json()["scenario"]["id"] == "1"


@pytest.mark.database
@requires_database
def test_with_no_parameter_the_picture_serves_the_newest_completed_run(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-013, api-002, db-007 -- amendment: the default is unchanged, so
    # api-002's guarantee, its parity test and the frontend are untouched
    _insert_run(hours_database, 1, generated_offset_s=0)
    _insert_run(hours_database, 2, generated_offset_s=600)

    with _client(hours_database, monkeypatch) as client:
        response = client.get(PICTURE_PATH)

    assert response.status_code == 200
    assert response.json()["scenario"]["id"] == "2"


@pytest.mark.database
@requires_database
def test_an_unknown_run_is_refused_and_never_served_as_the_newest(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: api-013 -- the sharpest failure case in the item.

    Falling back to the newest hour is indistinguishable from the feature
    working, which is exactly what makes it the dangerous implementation: the
    screen shows a picture, the picture is of an hour nobody asked for, and
    nothing anywhere says so.
    """
    # spec: api-013
    _insert_run(hours_database, 1)

    with _client(hours_database, monkeypatch) as client:
        response = client.get(PICTURE_PATH, params={"run": 999})

    assert response.status_code == 404
    assert "999" in response.text


@pytest.mark.database
@requires_database
def test_a_non_integer_run_is_refused_rather_than_defaulted(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-013, api-007 -- an unrecognised parameter value never silently
    # defaults, which is api-007's rule for the view filter one item along
    _insert_run(hours_database, 1)

    with _client(hours_database, monkeypatch) as client:
        response = client.get(PICTURE_PATH, params={"run": "latest"})

    assert response.status_code == 422


@pytest.mark.database
@requires_database
def test_a_requested_run_and_the_default_serve_one_shape(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-013 -- the named failure case: two shapes would split the
    # contract in two, and the parity test only ever sees one of them
    _insert_run(hours_database, 1)

    with _client(hours_database, monkeypatch) as client:
        default = client.get(PICTURE_PATH)
        named = client.get(PICTURE_PATH, params={"run": 1})

    assert set(default.json()) == set(named.json()) == _fields(OperationalPicture)


@pytest.mark.database
@requires_database
def test_an_incomplete_run_is_reachable_by_name_though_the_index_omits_it(
    hours_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: api-013, constraint 5 -- the asymmetry, asserted.

    Diagnosing a batch that half-failed is a legitimate thing to do from the
    screen, so the addressing mechanism reaches a run the chooser does not
    offer. Stated rather than left as an inconsistency somebody tidies away.
    """
    # spec: api-013, db-007
    _insert_run(hours_database, 1, completed=True, generated_offset_s=0)
    _insert_run(hours_database, 2, completed=False, generated_offset_s=600)

    with _client(hours_database, monkeypatch) as client:
        response = client.get(PICTURE_PATH, params={"run": 2})

    assert response.status_code == 200
    assert response.json()["scenario"]["id"] == "2"
    assert [entry["runId"] for entry in _hours(hours_database, monkeypatch)] == [1]
