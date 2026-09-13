"""The operational picture endpoint. Spec: api-002.

Four kinds of test, the same split `db-003` and `adp-007` use.

**Contract parity**, which is the item's whole point. The TypeScript contract
and the response models are two declarations of one shape, in two languages,
that no compiler checks against each other. The test parses the contract file
and compares field sets in both directions, so a field added on either side
without the other fails. It **raises rather than skips** when the contract is
not readable: `frontend/` is not mounted into the backend container by default,
and a skip here would be exactly the failure the test exists to catch, one
level up (`ops-003`, `adp-007`).

**Assembly**, over a pure function taking a run and a list of observations. All
of the payload's judgement lives there — the unit conversion, the data mode,
and what an absent detector is allowed to claim — so all of it is provable with
no database.

**The endpoint against a live database**, marked and skipped without one.

**One absence**, over the run summary: ground truth must not have a field to
leak through (`api-009`).

The detection summary is served as **null rather than a neutral band**. No
detector exists, and `Low` would be a claim about the data rather than a
statement about the system — the same reasoning that made `db-007`'s completion
flag nullable. `op-001` already requires the screen to render with scenario
data absent, so absence is a state the contract is expected to carry.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.api.v1.operational_picture import FINAL_WINDOW_SECONDS
from app.api.v1.schemas.operational_picture import (
    AircraftTrack,
    DetectionSummary,
    Hypothesis,
    OperationalPicture,
    RFSensor,
    Scenario,
    TimelineEvent,
    build_operational_picture,
)
from app.dal.models import (
    CanonicalObservation,
    DataMode,
    Location,
    ObservationType,
    Provenance,
    ScenarioRunSummary,
    SourceType,
    TrackPayload,
    ValidationStatus,
)
from app.db.migrations import alembic_config
from app.db.repository import PostgisObservationRepository
from app.main import app
from tests.conftest import live_database_url, requires_database
from tests.contracts import contract_paths
from tests.contracts import interfaces as _interfaces
from tests.contracts import read_contract as _read

CONTRACT_PATHS = contract_paths("operationalPicture.ts")

#: Interface name in the contract to the model that must mirror it. Names are
#: identical on both sides on purpose: a mapping table here would be a place for
#: the two to drift while every test still passed.
MODELS = {
    "Scenario": Scenario,
    "Hypothesis": Hypothesis,
    "DetectionSummary": DetectionSummary,
    "RFSensor": RFSensor,
    "AircraftTrack": AircraftTrack,
    "TimelineEvent": TimelineEvent,
    "OperationalPicture": OperationalPicture,
}

#: The two fields that carried `74.2` and `0.92` before this item, rendered as
#: "74.2%" and "0.92" on a screen (`FR-715`, `AC-11`).
DETECTION_FIELDS = ("anomalyLevel", "signalIntegrity")

HOUR_START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)

#: Cologne, from row 0 of the extract, and the metric altitude that comes with
#: it. 5753.1 m is 18,875 ft, which is not a round number in either unit — a
#: conversion that silently did nothing would still look plausible otherwise.
#: The expected value was first written as 18,874, from arithmetic done in my
#: head rather than by the machine, and the implementation was correct and the
#: test wrong. Corrected after the fact, which is a deviation from the order
#: this project works in and is recorded as one.
LAT, LON = 51.0905, 7.5473
ALTITUDE_M = 5753.1
ALTITUDE_FT = 18875

RUN_ID = 1


# ------------------------------------------------------------------- helpers


def _model_fields(model: Any) -> set[str]:
    return set(model.model_json_schema(by_alias=True)["properties"])


def _observation(
    *,
    aircraft_id: str = "AC-48089ab4e5a9",
    offset_s: int = 0,
    altitude_m: float | None = ALTITUDE_M,
    lat: float = LAT,
    lon: float = LON,
    data_mode: DataMode = DataMode.REPLAYED,
    run_id: int = RUN_ID,
) -> CanonicalObservation:
    return CanonicalObservation(
        source_id="opensky-replay",
        source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK,
        timestamp=HOUR_START + timedelta(seconds=offset_s),
        location=Location(lat=lat, lon=lon),
        data_mode=data_mode,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="opensky-replay",
            source_type=SourceType.OPENSKY,
            data_mode=data_mode,
            scenario_run_id=run_id,
        ),
        payload=TrackPayload(
            aircraft_id=aircraft_id,
            flight_id="FL-0c53755a34bc",
            altitude_m=altitude_m,
            velocity_ms=194.26,
            heading_deg=135.64,
            vertical_rate_ms=13.33,
            on_ground=False,
            position_staleness_s=1.06,
            contact_staleness_s=0.0,
        ),
    )


def _run(
    *, run_id: int = RUN_ID, completed: bool = True, scenario_type: str = "replay-only"
) -> ScenarioRunSummary:
    return ScenarioRunSummary(
        id=run_id,
        scenario_type=scenario_type,
        seed=0,
        started_at=HOUR_START,
        completed_at=HOUR_START + timedelta(seconds=10) if completed else None,
    )


# --------------------------------------------------------------- contract parity


def test_the_contract_is_read_rather_than_skipped() -> None:
    """The guard itself, tested.

    Every parity assertion below is worthless if the file cannot be found and
    the suite quietly reports success, which is what a `skipif` would do. The
    helper raises instead, and this is the test that says so.

    **This one passes before any implementation exists, and that is correct.**
    It asserts a property of the test file rather than of the system, so there
    is no implementation for it to fail against; it goes red if someone
    softens the helper into a skip, which is the only failure it is for.
    """
    # spec: api-002
    with pytest.raises(AssertionError, match="not found"):
        _read((Path("/nowhere/operationalPicture.ts"),))


def test_the_parser_finds_the_contract_it_claims_to_check() -> None:
    # spec: api-002 -- a parser that silently matched nothing would make every
    # comparison below a comparison of two empty sets, which passes
    interfaces = _interfaces(_read(CONTRACT_PATHS))

    assert set(interfaces) == set(MODELS)
    assert all(fields for fields in interfaces.values())


@pytest.mark.parametrize("name", sorted(MODELS))
def test_each_interface_and_its_model_carry_the_same_fields(name: str) -> None:
    # spec: api-002 -- the named failure case, in both directions: a field added
    # or dropped on either side without the other fails here
    interfaces = _interfaces(_read(CONTRACT_PATHS))

    assert set(interfaces[name]) == _model_fields(MODELS[name])


@pytest.mark.parametrize("field", DETECTION_FIELDS)
def test_the_detection_fields_are_not_numeric_in_the_contract(field: str) -> None:
    """`FR-715` and `AC-11`, asserted at the contract rather than at the screen.

    Both fields were numeric before this item, and the screen rendered them as
    "74.2%" and "0.92". Asserting only the rendering would leave the decimal on
    the wire for the next component to find.
    """
    # spec: api-002, FR-715, AC-11
    declared = _interfaces(_read(CONTRACT_PATHS))["DetectionSummary"][field]

    assert "number" not in declared


@pytest.mark.parametrize("field", DETECTION_FIELDS)
def test_the_detection_fields_are_not_numeric_in_the_response_model(
    field: str,
) -> None:
    # spec: api-002, FR-715 -- the same assertion on the Python side, because
    # the two declarations are what this item exists to keep in step
    schema = DetectionSummary.model_json_schema(by_alias=True)["properties"][field]

    assert "number" not in str(schema)
    assert "integer" not in str(schema)


# --------------------------------------------------------------------- assembly


def test_a_picture_with_no_run_carries_no_scenario_and_no_tracks() -> None:
    """An empty database is a 200 with an empty picture, not an error.

    `op-001` requires the screen to render its data-mode badge even when
    scenario data is absent, so absence is a state the contract is already
    expected to carry rather than one invented here.
    """
    # spec: api-002, op-001
    picture = build_operational_picture(run=None, observations=[])

    assert picture.scenario is None
    assert picture.aircraftTracks == []


@pytest.mark.parametrize("section", ["hypotheses", "rfSensors", "timelineEvents"])
def test_the_sections_with_no_producer_are_empty_rather_than_invented(
    section: str,
) -> None:
    # spec: api-002 -- no detector, no RF source and no generator exist. An
    # empty section is honest; a populated one would be invented data reaching
    # an analyst through a system whose argument is that this must not happen.
    picture = build_operational_picture(run=_run(), observations=[_observation()])

    assert getattr(picture, section) == []


@pytest.mark.parametrize("field", DETECTION_FIELDS)
def test_the_detection_summary_is_absent_rather_than_optimistic(field: str) -> None:
    """Null, not `Low`.

    `Low` is a claim about the data. With no detector in the system the only
    truthful value is the absence of one — the same reasoning that made
    `db-007`'s completion flag nullable rather than defaulted.
    """
    # spec: api-002, db-007
    picture = build_operational_picture(run=_run(), observations=[_observation()])

    assert getattr(picture.detectionSummary, field) is None


def test_altitude_is_converted_from_metres_to_feet() -> None:
    # spec: api-002 -- the store holds metres and the contract asks for feet.
    # 5753.1 m is 18,874 ft: a conversion that silently did nothing would still
    # produce a plausible-looking altitude, so the fixture value is one where
    # the two units are not confusable.
    picture = build_operational_picture(run=_run(), observations=[_observation()])

    assert picture.aircraftTracks[0].altitudeFt == ALTITUDE_FT


def test_a_track_with_no_altitude_survives_rather_than_being_dropped() -> None:
    # spec: api-002 -- 22.7% of positioned rows in the corpus carry no altitude,
    # and an aircraft with an unknown height is still an aircraft on the map
    picture = build_operational_picture(
        run=_run(), observations=[_observation(altitude_m=None)]
    )

    assert len(picture.aircraftTracks) == 1
    assert picture.aircraftTracks[0].altitudeFt is None


def test_the_track_name_is_the_pseudonym_it_was_stored_under() -> None:
    # spec: api-002, dal-004 -- the payload holds a pseudonym and the contract's
    # `name` is what a person reads on screen, so this is the field a real
    # identifier would surface in if one ever survived ingest
    picture = build_operational_picture(
        run=_run(), observations=[_observation(aircraft_id="AC-deadbeef0001")]
    )

    assert picture.aircraftTracks[0].name == "AC-deadbeef0001"


def test_the_data_mode_comes_from_the_observations_actually_served() -> None:
    # spec: api-002 -- reported rather than assumed. A run row does not record a
    # data mode; the observations do, and they are what is on the screen.
    picture = build_operational_picture(run=_run(), observations=[_observation()])

    assert picture.scenario is not None
    assert picture.scenario.dataMode == DataMode.REPLAYED.value


def test_observations_from_two_modes_are_reported_as_mixed() -> None:
    """Reported rather than resolved.

    Nothing produces a mixed batch today, and `scn-001` is what will: a
    scenario injects synthetic records into a replayed hour, so a run holds
    both. The failure this guards is a screen labelled `replayed` while showing
    injected records — a mislabel an analyst cannot see and has no reason to
    doubt, in a system whose premise is that they can tell.
    """
    # spec: api-002, scn-001
    picture = build_operational_picture(
        run=_run(),
        observations=[
            _observation(),
            _observation(aircraft_id="AC-injected", data_mode=DataMode.SYNTHETIC),
        ],
    )

    assert picture.scenario is not None
    assert picture.scenario.dataMode == "mixed"


def test_a_run_with_no_observations_reports_an_unknown_data_mode() -> None:
    # spec: api-002 -- the failure case for the line above: with nothing served,
    # naming a mode would be a guess
    picture = build_operational_picture(run=_run(), observations=[])

    assert picture.scenario is not None
    assert picture.scenario.dataMode == "unknown"


def test_the_scenario_reports_the_run_it_came_from() -> None:
    # spec: api-002 -- the id is what makes a screenshot traceable to a run
    picture = build_operational_picture(run=_run(run_id=8), observations=[])

    assert picture.scenario is not None
    assert picture.scenario.id == "8"


def test_the_run_summary_has_no_field_for_ground_truth() -> None:
    """`api-009`: the answer key never leaves the run record.

    Asserted on the model rather than on a payload, because a payload test only
    proves that this particular run had none. A model with no such field cannot
    carry one out on any run.

    **This passed against an empty stub during the red run**, which is what an
    absence assertion does and why the project mutation-tests them rather than
    trusting them: the result is recorded at the foot of this file.
    """
    # spec: api-002, api-009
    assert "ground_truth" not in ScenarioRunSummary.model_fields
    assert "groundTruth" not in _model_fields(ScenarioRunSummary)


# ------------------------------------------------------- against the database


@pytest.fixture
def picture_database() -> Engine:
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


def _insert_run(
    engine: Engine, run_id: int, *, completed: bool, started_offset_s: int = 0
) -> None:
    with engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at, completed_at) "
                "VALUES (:id, 'replay-only', '{}'::jsonb, 0, :started, :completed)"
            ),
            {
                "id": run_id,
                "started": HOUR_START + timedelta(seconds=started_offset_s),
                "completed": (
                    HOUR_START + timedelta(seconds=started_offset_s + 10)
                    if completed
                    else None
                ),
            },
        )
        connection.commit()


def _save(engine: Engine, observations: Sequence[CanonicalObservation]) -> None:
    PostgisObservationRepository(sessionmaker(bind=engine, autoflush=False)).save_batch(
        observations, []
    )


def _get(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        response = client.get("/api/v1/operational-picture")
    assert response.status_code == 200
    return dict(response.json())


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_the_six_sections(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-002
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, [_observation()])

    payload = _get(picture_database, monkeypatch)

    assert set(payload) == _model_fields(OperationalPicture)


@pytest.mark.database
@requires_database
def test_an_empty_database_serves_an_empty_picture_rather_than_failing(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-002 -- the named failure case. A screen that cannot render
    # before the first run is a screen nobody can develop against.
    payload = _get(picture_database, monkeypatch)

    assert payload["scenario"] is None
    assert payload["aircraftTracks"] == []


@pytest.mark.database
@requires_database
def test_the_endpoint_prefers_the_run_known_to_have_completed(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`db-007`, one day old, earning its place.

    The newer run is the one an ordinary "most recent" query would serve, and
    it is the one that never finished. Serving it means serving a partial hour
    as though it were a whole one.
    """
    # spec: api-002, db-007
    _insert_run(picture_database, 1, completed=True, started_offset_s=0)
    _insert_run(picture_database, 2, completed=False, started_offset_s=600)
    _save(picture_database, [_observation(run_id=1)])
    _save(picture_database, [_observation(run_id=2, aircraft_id="AC-000000000002")])

    payload = _get(picture_database, monkeypatch)

    assert payload["scenario"]["id"] == "1"
    assert [track["name"] for track in payload["aircraftTracks"]] == ["AC-48089ab4e5a9"]


@pytest.mark.database
@requires_database
def test_the_endpoint_falls_back_to_the_most_recent_run_when_none_completed(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-002 -- nothing has ever completed, so the alternative to serving
    # an unfinished run is serving nothing at all, which is worse
    _insert_run(picture_database, 1, completed=False, started_offset_s=0)
    _insert_run(picture_database, 2, completed=False, started_offset_s=600)

    payload = _get(picture_database, monkeypatch)

    assert payload["scenario"]["id"] == "2"


@pytest.mark.database
@requires_database
def test_only_the_latest_position_for_an_aircraft_is_served(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-002 -- an hour of replay holds roughly 140 positions per
    # aircraft. The screen wants where each one is, not everywhere it has been.
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(
        picture_database,
        [
            _observation(offset_s=0, lat=50.0),
            _observation(offset_s=30, lat=52.0),
            _observation(offset_s=10, lat=51.0),
        ],
    )

    payload = _get(picture_database, monkeypatch)

    assert len(payload["aircraftTracks"]) == 1
    assert payload["aircraftTracks"][0]["lat"] == pytest.approx(52.0)


@pytest.mark.database
@requires_database
def test_positions_older_than_the_final_window_are_not_served(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-002 -- an aircraft last seen fifty minutes ago is not currently
    # in the sector, and drawing it as though it were is the map lying
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(
        picture_database,
        [
            _observation(aircraft_id="AC-recent", offset_s=3600),
            _observation(
                aircraft_id="AC-stale", offset_s=3600 - FINAL_WINDOW_SECONDS - 60
            ),
        ],
    )

    payload = _get(picture_database, monkeypatch)

    assert [track["name"] for track in payload["aircraftTracks"]] == ["AC-recent"]


@pytest.mark.database
@requires_database
def test_no_source_identifier_reaches_the_payload(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-002, dal-004 -- the last point at which a real identifier could
    # still escape, and the only one where an analyst would see it
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, [_observation()])

    payload = _get(picture_database, monkeypatch)

    assert "icao24" not in str(payload)
    assert "callsign" not in str(payload)


@pytest.mark.database
@requires_database
def test_the_payload_carries_no_decimal_score(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-002, FR-715, AC-11 -- asserted on the wire, not only on the two
    # declarations, because this is the form an analyst would actually receive
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, [_observation()])

    summary = _get(picture_database, monkeypatch)["detectionSummary"]

    assert all(
        value is None or value in {"Low", "Medium", "High"}
        for value in summary.values()
    )


# Mutation results, 2026-09-04. Three of the assertions above claim an absence
# or a preference, and would each pass against a plausible wrong implementation:
#
#   * adding a `ground_truth` field to `ScenarioRunSummary` turned
#     `..._has_no_field_for_ground_truth` red -- it had passed against an empty
#     stub during the red run, which is what an absence assertion does;
#   * adding a field to the TypeScript contract and nowhere else turned exactly
#     one parity case red, `[Scenario]`, and left the other six green;
#   * removing `(completed_at IS NOT NULL) DESC` from the run query -- the
#     ordinary "most recent run" a reasonable person would write -- turned
#     `..._prefers_the_run_known_to_have_completed` red and nothing else.
#
# On the frontend side, restoring the percentage sign to the anomaly label
# turned three of the six screen tests red, including the whole-screen
# assertion that no percentage appears anywhere (AC-11).
