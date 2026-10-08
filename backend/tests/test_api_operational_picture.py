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

import ast
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.api.v1.operational_picture import FINAL_WINDOW_SECONDS
from app.api.v1.schemas import operational_picture as picture_module
from app.api.v1.schemas.operational_picture import (
    PERSISTED_PRODUCERS,
    AircraftTrack,
    DetectionCount,
    DetectionSummary,
    Hypothesis,
    OperationalPicture,
    PictureError,
    PictureView,
    RFSensor,
    Scenario,
    SelectableHour,
    SuppressedCounts,
    TimelineEvent,
    build_operational_picture,
)
from app.dal.models import (
    CanonicalObservation,
    DataMode,
    DetectionPass,
    Location,
    ObservationType,
    Provenance,
    ScenarioRunSummary,
    SourceType,
    TrackPayload,
    ValidationStatus,
)
from app.db.findings import save_findings
from app.db.migrations import alembic_config
from app.db.repository import PostgisObservationRepository, record_detection_pass
from app.detection.clustering import FINDING_TYPE as CLUSTER_TYPE
from app.detection.clustering import RULE_ID as CLUSTER_RULE
from app.detection.control import REGISTER, Kind, Producer, build_register
from app.detection.findings import DetectionFinding
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE_TYPE
from app.detection.fusion import RULE_ID as FUSION_RULE
from app.detection.rate_excess import FINDING_TYPE as EXCESS_TYPE
from app.detection.rf_noise import ANOMALY_TYPE as RF_TYPE
from app.detection.rf_noise import RULE_ID as RF_RULE
from app.detection.rf_noise import Severity
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT_TYPE
from app.detection.sensor_fault import RULE_ID as FAULT_RULE
from app.detection.track_gap import FINDING_TYPE as GAP_TYPE
from app.detection.track_gap import RULE_ID as GAP_RULE
from app.main import app
from app.scenario.layout import load_layout
from tests.conftest import live_database_url, requires_database
from tests.contracts import contract_paths, union_members
from tests.contracts import interfaces as _interfaces
from tests.contracts import read_contract as _read

CONTRACT_PATHS = contract_paths("operationalPicture.ts")

#: Interface name in the contract to the model that must mirror it. Names are
#: identical on both sides on purpose: a mapping table here would be a place for
#: the two to drift while every test still passed.
MODELS = {
    "Scenario": Scenario,
    "Hypothesis": Hypothesis,
    "DetectionCount": DetectionCount,
    "DetectionSummary": DetectionSummary,
    "RFSensor": RFSensor,
    "AircraftTrack": AircraftTrack,
    "TimelineEvent": TimelineEvent,
    "OperationalPicture": OperationalPicture,
    # `api-013`. Declared in the picture's own contract rather than in a file
    # of its own, so this parser check -- every interface has a model, both
    # directions -- covers the new shape the moment it exists, instead of a
    # second parity suite that can drift from this one.
    "SelectableHour": SelectableHour,
    # `api-007`. The view metadata, so the withheld counts are held to the
    # contract by the same check as every other shape.
    "PictureView": PictureView,
    "SuppressedCounts": SuppressedCounts,
    # `api-017`. Looked up rather than imported, so the shapes going missing
    # fails the parity tests one by one instead of the whole module at
    # collection.
    "InterferenceZone": getattr(picture_module, "InterferenceZone", None),
    "ZoneCentre": getattr(picture_module, "ZoneCentre", None),
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

#: `scn-005`'s shipped layout: seven receivers, eight channels, one band. The
#: picture serves the receivers from here rather than from the findings, so a
#: quiet run still has a map with reference points on it.
LAYOUT = load_layout()
RECEIVER = LAYOUT.sensors[0].sensor_id
OTHER_RECEIVER = LAYOUT.sensors[1].sensor_id


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
    picture = build_operational_picture(layout=LAYOUT, run=None, observations=[])

    assert picture.scenario is None
    assert picture.aircraftTracks == []


@pytest.mark.parametrize("section", ["hypotheses", "timelineEvents"])
def test_the_sections_with_no_producer_are_empty_rather_than_invented(
    section: str,
) -> None:
    """`api-002`'s rule, kept, over a shorter list.

    An empty section is honest; a populated one would be invented data reaching
    an analyst through a system whose argument is that this must not happen.
    `api-012` closed `timelineEvents` by giving it a producer, so it is empty
    here because this picture was handed no findings -- a different fact from
    the one `api-002` recorded. `hypotheses` is the last section whose emptiness
    is still a statement about the system.

    `rfSensors` has left this list rather than this rule: the receivers are
    `scn-005`'s layout, configuration the generator itself reads, so serving
    them invents nothing. What would be invented is a *health* reading, and that
    is the field the detection stamp governs.
    """
    # spec: api-002, api-012
    picture = build_operational_picture(
        layout=LAYOUT, run=_run(), observations=[_observation()]
    )

    assert getattr(picture, section) == []


def test_the_detection_summary_is_absent_rather_than_optimistic() -> None:
    """Null, not `Low` -- and now the whole summary rather than its two fields.

    `Low` is a claim about the data; absence is a statement about the system,
    which is the only one that can be made truthfully about a run nothing has
    examined. `api-002` carried that on the fields. `api-012` moved it onto the
    object, because the fields would otherwise carry a second meaning the store
    cannot establish: `anom-001`'s unjudged cells are not persisted, so from the
    findings table "judged everything, found nothing" and "judged nothing" are
    the same empty result. One absence, one meaning.
    """
    # spec: api-002, api-012, db-007
    picture = build_operational_picture(
        layout=LAYOUT, run=_run(), observations=[_observation()]
    )

    assert picture.detectionSummary is None


def test_altitude_is_converted_from_metres_to_feet() -> None:
    # spec: api-002 -- the store holds metres and the contract asks for feet.
    # 5753.1 m is 18,874 ft: a conversion that silently did nothing would still
    # produce a plausible-looking altitude, so the fixture value is one where
    # the two units are not confusable.
    picture = build_operational_picture(
        layout=LAYOUT, run=_run(), observations=[_observation()]
    )

    assert picture.aircraftTracks[0].altitudeFt == ALTITUDE_FT


def test_a_track_with_no_altitude_survives_rather_than_being_dropped() -> None:
    # spec: api-002 -- 22.7% of positioned rows in the corpus carry no altitude,
    # and an aircraft with an unknown height is still an aircraft on the map
    picture = build_operational_picture(
        layout=LAYOUT, run=_run(), observations=[_observation(altitude_m=None)]
    )

    assert len(picture.aircraftTracks) == 1
    assert picture.aircraftTracks[0].altitudeFt is None


def test_the_track_name_is_the_pseudonym_it_was_stored_under() -> None:
    # spec: api-002, dal-004 -- the payload holds a pseudonym and the contract's
    # `name` is what a person reads on screen, so this is the field a real
    # identifier would surface in if one ever survived ingest
    picture = build_operational_picture(
        layout=LAYOUT,
        run=_run(),
        observations=[_observation(aircraft_id="AC-deadbeef0001")],
    )

    assert picture.aircraftTracks[0].name == "AC-deadbeef0001"


def test_the_data_mode_comes_from_the_observations_actually_served() -> None:
    # spec: api-002 -- reported rather than assumed. A run row does not record a
    # data mode; the observations do, and they are what is on the screen.
    picture = build_operational_picture(
        layout=LAYOUT, run=_run(), observations=[_observation()]
    )

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
        layout=LAYOUT,
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
    picture = build_operational_picture(layout=LAYOUT, run=_run(), observations=[])

    assert picture.scenario is not None
    assert picture.scenario.dataMode == "unknown"


def test_the_scenario_reports_the_run_it_came_from() -> None:
    # spec: api-002 -- the id is what makes a screenshot traceable to a run
    picture = build_operational_picture(
        layout=LAYOUT, run=_run(run_id=8), observations=[]
    )

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
    """`FR-715`, `AC-11`, on the wire rather than on the two declarations.

    Scored, which is `api-012`'s correction to this test rather than a
    convenience: before it, the summary this fetched was null on every run, so
    the assertion ran over two nulls and held whatever the levels would have
    been. An absence assertion over an absent object is the vacuous pass this
    project keeps finding -- and the only payload that can carry a decimal is
    the one that carries readings.
    """
    # spec: api-002, api-012, FR-715, AC-11
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, [_observation()])
    factory = sessionmaker(bind=picture_database, autoflush=False)
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=RF_RULE,
        findings=[_rf()],
        policy={"RF-NOISE.threshold_db": "6.0"},
    )
    record_detection_pass(factory, RUN_ID, policy={"RF-NOISE.threshold_db": "6.0"})

    summary = _get(picture_database, monkeypatch)["detectionSummary"]

    assert summary is not None, "a scored run served no summary to check"
    assert summary["anomalyLevel"] in {"Low", "Medium", "High"}
    assert summary["signalIntegrity"] in {"Low", "Medium", "High"}
    # Over the counts too, because a count is the one place a number belongs
    # here and so the one place a decimal could pass for a reading.
    for entry in summary["counts"]:
        assert entry["count"] is None or isinstance(entry["count"], int)
        assert not isinstance(entry["count"], float)


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


# ---------------------------------------------------- detection on the picture
#
# Spec: api-012. Three collections `api-002` has always served empty, and the
# justification it served them under -- "because no detector, RF source or
# generator exists" -- expired without anything noticing, because three items
# consume these fields and none produced them.
#
# The sharpest constraint is about zero, and it is `anom-008`'s argument at the
# API boundary: a quiet run, a run nobody examined, and a pass pointed at the
# wrong observations all produce no detections, and three of those are failures
# no property of the output separates. So the payload reports *unscored* and
# *clean* differently, and what carries the distinction is the presence of the
# account rather than any number in it.


def _detection_pass(policy: dict[str, str] | None = None) -> DetectionPass:
    return DetectionPass(
        scenario_run_id=RUN_ID,
        at=HOUR_START + timedelta(seconds=30),
        policy=policy or {"RF-NOISE.threshold_db": "6.0"},
    )


def _finding(
    *,
    rule_id: str,
    finding_type: str,
    subject: str,
    offset_s: int = 0,
    details: dict[str, Any] | None = None,
) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=RUN_ID,
        rule_id=rule_id,
        finding_type=finding_type,
        subject=subject,
        started_at=HOUR_START + timedelta(seconds=offset_s),
        ended_at=HOUR_START + timedelta(seconds=offset_s + 300),
        location=Location(lat=LAT, lon=LON),
        details=details or {},
    )


def _rf(sensor: str = RECEIVER, *, channel: int = 0, severity: str = "high"):
    return _finding(
        rule_id=RF_RULE,
        finding_type=RF_TYPE,
        subject=f"{sensor}:{channel}",
        details={"severity": severity, "metric": "power_dbm"},
    )


def _fault(sensor: str = RECEIVER, *, offset_s: int = 0):
    return _finding(
        rule_id=FAULT_RULE,
        finding_type=FAULT_TYPE,
        subject=sensor,
        offset_s=offset_s,
        details={"confidence": "high"},
    )


def _zone(*sensors: str, offset_s: int = 0):
    return _finding(
        rule_id=FUSION_RULE,
        finding_type=INTERFERENCE_TYPE,
        subject=sensors[0],
        offset_s=offset_s,
        details={"confidence": "medium", "sensors": list(sensors)},
    )


def _gap(aircraft: str = "AC-48089ab4e5a9"):
    return _finding(
        rule_id=GAP_RULE, finding_type=GAP_TYPE, subject=aircraft, details={}
    )


def _scored(
    findings: Sequence[DetectionFinding] = (), **kwargs: Any
) -> OperationalPicture:
    """A picture for a run the pass has examined."""
    kwargs.setdefault("run", _run())
    kwargs.setdefault("observations", [_observation()])
    return build_operational_picture(
        layout=LAYOUT,
        findings=findings,
        detection_pass=_detection_pass(),
        **kwargs,
    )


def _count_for(picture: OperationalPicture, key: tuple[str, str]) -> DetectionCount:
    assert picture.detectionSummary is not None
    found = [
        c for c in picture.detectionSummary.counts if (c.ruleId, c.findingType) == key
    ]
    assert len(found) == 1, f"{key} appears {len(found)} times in the account"
    return found[0]


# ------------------------------------------------- unscored is not the same as clean


def test_an_unscored_run_and_a_quiet_run_do_not_produce_the_same_payload() -> None:
    """The item's sharpest constraint, and `anom-008` at the API boundary.

    Zero is the answer a quiet run gives and also the answer a pipeline that
    never ran gives, and most of those cases are failures no property of the
    output can separate. The findings write replaces per run per rule *including
    at zero*, so the table itself cannot tell them apart -- which is why the
    distinction rests on `anom-015`'s run stamp and not on a count.
    """
    # spec: api-012, anom-008, anom-015
    unscored = build_operational_picture(
        layout=LAYOUT, run=_run(), observations=[_observation()]
    )
    clean = _scored()

    assert unscored.detectionSummary is None
    assert clean.detectionSummary is not None
    assert unscored.model_dump() != clean.model_dump()


def test_a_quiet_run_is_reported_clean_rather_than_silent() -> None:
    """Spec: api-012, anom-008.

    A pass that found nothing still accounts for every producer. The account is
    what says the detectors looked; the zeroes in it are the result.
    """
    # spec: api-012, anom-008
    summary = _scored().detectionSummary

    assert summary is not None
    assert summary.counts, "a scored run carried no account at all"
    assert _count_for(_scored(), (RF_RULE, RF_TYPE)).count == 0


# ------------------------------------------------------------------- the account


def test_the_account_carries_every_registered_producer() -> None:
    """Spec: api-012, anom-008.

    `anom-008` refuses to grade a run against an account missing a producer,
    because a detector that never ran and one that found nothing are
    indistinguishable from the output. The same completeness is what makes this
    payload answerable, and the register is the one place that list lives.
    """
    # spec: api-012, anom-008
    summary = _scored().detectionSummary

    assert summary is not None
    assert {(c.ruleId, c.findingType) for c in summary.counts} == set(REGISTER)


def test_an_unbuilt_rule_reports_no_count_rather_than_zero() -> None:
    """Spec: api-012, anom-008, anom-006.

    `anom-008`'s own words: reporting zero across quiet runs "quotes the absence
    of a rule as the accuracy of one". A zero here is a figure that cannot be
    wrong, because nothing produced it.

    The register is injected rather than taken from the module, so this test
    keeps asserting the rule rather than the current state of `anom-006`.
    """
    # spec: api-012, anom-008
    register = build_register(
        Producer(rule_id=FAULT_RULE, finding_type=FAULT_TYPE, kind=Kind.REPORTABLE),
        Producer(
            rule_id="SOURCE-GAP",
            finding_type="possible_data_source_issue",
            kind=Kind.REPORTABLE,
            built=False,
        ),
    )

    entry = _count_for(
        _scored(register=register), ("SOURCE-GAP", "possible_data_source_issue")
    )

    assert entry.count is None
    assert entry.unavailable == "rule-not-built"


def test_a_producer_whose_output_is_not_persisted_is_not_reported_as_unbuilt() -> None:
    """Spec: api-012, anom-004, anom-012.

    Two registered producers leave no rows: `anom-004`'s clusters are
    deliberately unstored because their citation shape `evb-002` refuses by
    name, and `anom-012`'s rate excess is internal to the fusion decision. Both
    ran. Collapsing that into the unbuilt case would report a built detector as
    a missing one, which is the opposite of what the account is for.
    """
    # spec: api-012, anom-004, anom-012
    clusters = _count_for(_scored(), (CLUSTER_RULE, CLUSTER_TYPE))
    excess = _count_for(_scored(), (GAP_RULE, EXCESS_TYPE))

    for entry in (clusters, excess):
        assert entry.count is None
        assert entry.unavailable == "not-persisted"


def test_a_count_and_a_reason_for_its_absence_are_mutually_exclusive() -> None:
    """Spec: api-012, evb-001.

    Both directions refused at construction, on `EvidenceItem.grounding`'s rule:
    a declaration that can be a lie either way is not a declaration. A count
    beside a reason is unreadable, and neither is an absence nothing names.
    """
    # spec: api-012, evb-001
    common = {"ruleId": FAULT_RULE, "findingType": FAULT_TYPE, "kind": "reportable"}

    with pytest.raises(ValidationError):
        DetectionCount(**common, count=0, unavailable="not-persisted")
    with pytest.raises(ValidationError):
        DetectionCount(**common, count=None, unavailable=None)


def test_the_account_labels_an_intermediate_finding_as_intermediate() -> None:
    """Spec: api-012, anom-010.

    A quiet run genuinely holds about 138 track discontinuities, because
    aircraft stop reporting for ordinary reasons. An analyst shown that as an
    anomaly count reads a correct non-detection as a storm -- and a payload
    that did not carry the distinction would force the screen to hard-code a
    list of rule names, which outlives the reason it was written.
    """
    # spec: api-012, anom-010, anom-008
    picture = _scored([_gap(), _gap("AC-000000000002")])

    assert _count_for(picture, (GAP_RULE, GAP_TYPE)).kind == "intermediate"
    assert _count_for(picture, (GAP_RULE, GAP_TYPE)).count == 2
    assert _count_for(picture, (FAULT_RULE, FAULT_TYPE)).kind == "reportable"


def test_the_account_keys_on_the_pair_and_not_on_the_rule() -> None:
    """Spec: api-012, ai-001, anom-012.

    `anom-012` borrows `anom-010`'s rule id, so a rate excess and a
    discontinuity are identical by rule id while making different claims. The
    fourth place in this project that collision has had to be handled.

    **The fixture has to carry both halves of the collision.** Written with one
    discontinuity and nothing else, this test passed against an account keyed on
    the rule alone -- one `TRACK-GAP` finding is one either way -- and the
    mutation pass found it. That is the third time a one-item fixture has hidden
    a defect here, after `anom-009` and `anom-015`, and the shape is now a
    standing caution: a suite is weakest exactly where its fixtures are
    simplest.
    """
    # spec: api-012, ai-001, anom-012
    picture = _scored(
        [
            _gap(),
            _finding(
                rule_id=GAP_RULE, finding_type=EXCESS_TYPE, subject="RF-01", details={}
            ),
        ]
    )

    assert _count_for(picture, (GAP_RULE, GAP_TYPE)).count == 1
    # Not persisted, so it carries no count either way -- which is why the
    # assertion that matters is the one above: keyed on the rule, it reads 2.
    assert _count_for(picture, (GAP_RULE, EXCESS_TYPE)).count is None


# -------------------------------------------------------------------- the levels


def test_the_worst_deviation_sets_the_anomaly_level() -> None:
    """Spec: api-012, anom-001, FR-715.

    The level qualifies the **deviation**, which is the only thing the detection
    layer measures a magnitude for, and it is the worst one rather than an
    average: an average over the channels a receiver reports on falls as the
    quiet channels outnumber the loud one.
    """
    # spec: api-012, anom-001
    picture = _scored(
        [
            _rf(channel=0, severity="low"),
            _rf(channel=1, severity="high"),
            _rf(channel=2, severity="medium"),
        ]
    )

    assert picture.detectionSummary is not None
    assert picture.detectionSummary.anomalyLevel == "High"


def test_a_scored_run_with_no_deviation_reports_the_lowest_level() -> None:
    # spec: api-012, anom-008 -- the summary's presence is what says a pass ran,
    # so inside one every value is a reading rather than a stand-in for absence
    picture = _scored()

    assert picture.detectionSummary is not None
    assert picture.detectionSummary.anomalyLevel == "Low"


def test_a_level_the_detection_layer_does_not_spell_is_refused() -> None:
    """Spec: api-012, ai-002.

    Joined by **enum member name**, which is `ai-002`'s rule: `.title()` would
    launder any word at all into something that looks valid and fails later, at
    a boundary that no longer holds the row it came from.
    """
    # spec: api-012, ai-002
    with pytest.raises(PictureError, match="severe"):
        _scored([_rf(severity="severe")])


@pytest.mark.parametrize("severity", [s for s in Severity])
def test_every_severity_the_detection_layer_can_produce_has_a_level(
    severity: Severity,
) -> None:
    # spec: api-012, anom-001 -- a fourth severity added to the rule must not
    # reach this boundary as a refusal on a legitimate run
    picture = _scored([_rf(severity=severity.value)])

    assert picture.detectionSummary is not None
    assert picture.detectionSummary.anomalyLevel in ("Low", "Medium", "High")


def test_signal_integrity_reads_the_receivers_and_not_the_deviations() -> None:
    """Spec: api-012, anom-007.

    The two readings stay two readings. `anom-007` is explicit that confidence
    qualifies the **attribution** while severity qualifies the **deviation**, so
    a single figure over both describes neither -- and this one is about the
    state of the receiver layout, which is one kind of thing.
    """
    # spec: api-012, anom-007
    nominal = _scored()
    deviating = _scored([_rf()])
    faulted = _scored([_rf(), _fault()])

    assert nominal.detectionSummary is not None
    assert deviating.detectionSummary is not None
    assert faulted.detectionSummary is not None
    assert nominal.detectionSummary.signalIntegrity == "High"
    assert deviating.detectionSummary.signalIntegrity == "Medium"
    assert faulted.detectionSummary.signalIntegrity == "Low"


# ----------------------------------------------------------------- the receivers


def test_the_receivers_come_from_the_layout_rather_than_from_the_findings() -> None:
    """Spec: api-012, scn-005.

    All seven, whether or not any of them was found to be deviating. Built the
    other way the strip would show only the receivers in trouble, which on a
    quiet run is an empty map and on a staged one is a map with no reference
    points to read the incident against.
    """
    # spec: api-012, scn-005
    picture = _scored([_rf()])

    assert [s.id for s in picture.rfSensors] == [
        site.sensor_id for site in LAYOUT.sensors
    ]
    assert {s.signalId for s in picture.rfSensors} == {
        channel.band for channel in LAYOUT.channels
    }


def test_a_receiver_state_is_unknown_until_a_pass_has_run() -> None:
    """Spec: api-012, anom-008.

    The same two-valued rule as the summary, on the field that carries a claim:
    a receiver reported `nominal` on a run nothing examined is a reassurance
    nothing checked, which is `api-002`'s own argument for `scenario.health`.
    """
    # spec: api-012, api-002
    picture = build_operational_picture(
        layout=LAYOUT, run=_run(), observations=[_observation()]
    )

    assert {s.health for s in picture.rfSensors} == {"unknown"}


def test_a_receiver_reports_the_worst_thing_said_about_it() -> None:
    """Spec: api-012, anom-007.

    A faulted receiver is also a deviating one -- the fault rule reads the radio
    rule's episodes -- so the two states are not exclusive and the attribution
    is the one that matters. Reported the other way round, a broken receiver
    reads as a loud one.
    """
    # spec: api-012, anom-007
    picture = _scored([_rf(), _rf(OTHER_RECEIVER), _fault()])
    health = {sensor.id: sensor.health for sensor in picture.rfSensors}

    assert health[RECEIVER] == "fault"
    assert health[OTHER_RECEIVER] == "deviating"
    assert health[LAYOUT.sensors[2].sensor_id] == "nominal"


def test_a_receiver_inside_an_interference_zone_is_deviating_and_not_faulted() -> None:
    """Spec: api-012, anom-005, anom-007.

    An interference zone is `anom-007`'s *environmental* verdict: more than one
    receiver deviated together, and the rule declined to blame any of them. A
    zone that marked its receivers faulty would report the opposite of what the
    ladder decided -- and the zone names all of them, because its window is the
    union of theirs.
    """
    # spec: api-012, anom-005
    picture = _scored([_zone(RECEIVER, OTHER_RECEIVER)])
    health = {sensor.id: sensor.health for sensor in picture.rfSensors}

    assert health[RECEIVER] == "deviating"
    assert health[OTHER_RECEIVER] == "deviating"


# ------------------------------------------------------------------ the timeline


def test_the_timeline_carries_the_reportable_claims_oldest_first() -> None:
    # spec: api-012, op-006 -- ordering is by event time and independent of the
    # order the rows came back in
    picture = _scored(
        [_fault(offset_s=600), _zone(OTHER_RECEIVER, offset_s=0), _fault(offset_s=300)]
    )

    assert [event.time for event in picture.timelineEvents] == sorted(
        event.time for event in picture.timelineEvents
    )
    assert len(picture.timelineEvents) == 3


def test_the_timeline_carries_no_intermediate_findings() -> None:
    """Spec: api-012, anom-010, anom-013.

    A quiet run holds about 138 discontinuities and four clusters. A timeline
    that listed them would bury the one line that is a conclusion, and would
    present working material to an analyst as an event.
    """
    # spec: api-012, anom-010
    picture = _scored([_gap(), _rf(), _fault()])

    assert [event.event for event in picture.timelineEvents] == [FAULT_TYPE]


def test_a_timeline_event_carries_the_finding_type_verbatim() -> None:
    """Spec: api-012, api-011, ai-001.

    Facts and never prose, which is `api-011`'s rule for the batch refusal: the
    screen composes its sentence where the rest of that screen's copy lives, and
    the payload stays assertable field by field. The vocabulary is `ai-001`'s,
    shared with the grounding check and the scoring pack.
    """
    # spec: api-012, api-011, ai-001
    picture = _scored([_zone(RECEIVER, OTHER_RECEIVER)])

    assert [event.event for event in picture.timelineEvents] == [INTERFERENCE_TYPE]
    assert [event.source for event in picture.timelineEvents] == [RECEIVER]


# ------------------------------------------------------------- no ground truth


def test_the_scenario_name_is_not_the_scenario_type() -> None:
    """`api-009`'s named failure case, which this endpoint was live with.

    `api-002` served `scenario.name` from the run's recorded type, so the
    screen's heading read `gnss-degradation` -- the name of the thing injected
    into the data the detectors are being measured against. It survived because
    `ScenarioRunSummary` was built with no ground-truth field and the check
    stopped there: the type is not the event, it is the **label** for it, and it
    discloses everything the event would.
    """
    # spec: api-012, api-009
    picture = build_operational_picture(
        layout=LAYOUT,
        run=_run(run_id=8, scenario_type="gnss-degradation"),
        observations=[_observation(run_id=8)],
    )

    assert picture.scenario is not None
    assert "gnss" not in picture.scenario.name.lower()
    assert "8" in picture.scenario.name


@pytest.mark.parametrize(
    "scenario_type",
    [
        "normal-baseline",
        "gnss-degradation",
        "aircraft-coverage-gap",
        "sensor-fault",
        "ambiguous-mixed-evidence",
    ],
)
def test_no_field_anywhere_in_the_payload_carries_the_scenario_type(
    scenario_type: str,
) -> None:
    """Spec: api-012, api-009.

    Asserted over the **serialised payload** rather than over the one field that
    held it, because the failure case says "whether as a field, a label or an
    inferable artefact" and a per-field test only ever proves the field somebody
    thought of. Every one of the five arms, because a check written against one
    is a check against the author's model of which one leaks.
    """
    # spec: api-012, api-009
    picture = _scored(
        [_fault()],
        run=_run(scenario_type=scenario_type),
    )

    assert scenario_type not in json.dumps(picture.model_dump(mode="json"))


# ------------------------------------------- the scenario block loses a field


#: Every field the scenario block carries after `api-014`, asserted exactly.
SCENARIO_FIELDS = {"id", "name", "dataMode"}


def test_the_scenario_block_carries_no_health_field() -> None:
    """Spec: api-014.

    The field was hard-coded to `unknown` with a comment recording that no
    health monitoring existed. What changed is not that a producer arrived but
    that another field took the job: `api-012`'s `signalIntegrity` is the state
    of the receiver layout, has a producer, and is the run-level health signal
    this one would have carried. Two health fields where one works is worse
    than one, because the broken one reads as a second fact that never arrives.
    """
    # spec: api-014, api-012, api-002
    assert _model_fields(Scenario) == SCENARIO_FIELDS


def test_the_contract_declares_no_scenario_health_either() -> None:
    # spec: api-014 -- the named failure case, one direction. The parity test
    # above catches a mismatch; this says which side is right, so a removal
    # that happened only in Python cannot be "fixed" by putting it back here.
    assert set(_interfaces(_read(CONTRACT_PATHS))["Scenario"]) == SCENARIO_FIELDS


def test_the_field_is_absent_rather_than_optional() -> None:
    """Spec: api-014 -- the named failure case.

    Making it nullable would leave the contract able to express a value nothing
    produces, which is the state the removal exists to end rather than a smaller
    version of it. A nullable field still appears among the schema's properties,
    so this is asserted there.

    **Over the properties and not over the whole schema**, which is a correction
    the first green run forced: written as a substring search across the
    serialised schema, this test failed on the docstring explaining the removal.
    Pydantic carries a model's docstring into its schema as `description`, so a
    string scan of a schema is also a scan of its own documentation -- the same
    shape as the checks in this repository that were satisfied by a comment, and
    the reason those were rewritten to parse rather than to search.
    """
    # spec: api-014
    properties = Scenario.model_json_schema(by_alias=True)["properties"]

    assert not any("health" in name.lower() for name in properties)
    assert not any("null" in str(schema) for schema in properties.values())


def test_no_scenario_in_a_served_payload_carries_health() -> None:
    # spec: api-014 -- over the serialised payload, because a route is free to
    # add a key the model does not declare
    picture = _scored([_fault()])

    assert picture.scenario is not None
    assert set(picture.model_dump(mode="json")["scenario"]) == SCENARIO_FIELDS


def test_an_empty_picture_carries_no_scenario_at_all() -> None:
    # spec: api-014, api-002 -- the removal must not turn a null scenario into
    # an object with two of its three fields
    picture = build_operational_picture(run=None, observations=[], layout=LAYOUT)

    assert picture.scenario is None


def test_the_receivers_keep_their_own_health() -> None:
    """Spec: api-014 -- the one real risk in this removal, asserted.

    `rfSensors[].health` has a producer, carries per-receiver state, and is what
    the screen renders for each of `scn-005`'s seven receivers. A removal that
    took both would delete a working signal alongside a broken one, and the two
    are spelled identically.
    """
    # spec: api-014, api-012, scn-005
    picture = _scored([_fault()])

    assert len(picture.rfSensors) == len(LAYOUT.sensors)
    assert all(sensor.health for sensor in picture.rfSensors)
    assert "health" in _model_fields(RFSensor)


def test_the_run_level_health_signal_still_exists_under_its_own_name() -> None:
    # spec: api-014 -- the removal is only honest because another field does the
    # job. If this ever stops being true the field was deleted, not superseded.
    summary = _scored([_fault()]).detectionSummary

    assert summary is not None
    assert summary.signalIntegrity in {"Low", "Medium", "High"}


def test_the_hypotheses_stay_empty() -> None:
    """Spec: api-012, api-002.

    155 hypothesis rows exist, so the condition that justified the other three
    empty sections has expired here too. What holds this one is a decision with
    its own failure cases -- which arm an analyst sees, whether a row whose
    grounding check FAILED may be shown at all -- and so its own item. Named
    rather than left silent, because the lesson of `api-002`'s amendment is that
    a producer-less field is invisible in a backlog.
    """
    # spec: api-012, api-002, db-002
    assert _scored([_fault()]).hypotheses == []


def test_the_two_new_unions_match_their_literals_on_both_sides() -> None:
    """Spec: api-012, api-002.

    Two closed sets reach the frontend as union types, and a closed set that is
    not compared against its origin is a list somebody edits one side of. The
    same argument `scn-004` makes for the five scenario type ids.
    """
    # spec: api-012, api-002
    source = _read(CONTRACT_PATHS)

    assert set(union_members(source, "ProducerKind")) == {k.value for k in Kind}
    assert set(union_members(source, "CountUnavailable")) == {
        "rule-not-built",
        "not-persisted",
    }


def test_the_reportable_finding_types_match_the_register_on_both_sides() -> None:
    """Spec: op-003 -- the closed set the screen's copy is held to.

    The screen has to turn each reportable finding type into a sentence, and a
    copy map that misses one prints the raw token at an analyst -- which is the
    defect that item exists to fix, so it must be impossible rather than
    unlikely. The set reaches the frontend as a union type and is compared
    against `anom-008`'s register here, the same way `api-012`'s two unions and
    `scn-004`'s five scenario ids are held.

    **This test is in the backend suite although the file it reads is in
    `frontend/`**, because the TypeScript parser exists once and on this side.
    Recorded because the mutation pass over `op-001` scored a mutant in that
    file as surviving vitest, which could not see it: where a file lives and
    which suite guards it are different facts.
    """
    # spec: op-003, op-006, api-012, anom-008
    declared = {
        producer.finding_type
        for producer in REGISTER.values()
        if producer.kind is Kind.REPORTABLE
    }

    declared_in_contract = union_members(_read(CONTRACT_PATHS), "ReportableFindingType")

    assert set(declared_in_contract) == declared


def test_the_reportable_set_is_the_three_the_ladder_can_claim() -> None:
    # spec: op-003, anom-013 -- spelled out as well as derived, so a register
    # that loses a reportable producer fails here rather than agreeing with a
    # contract that lost the same one
    declared = {
        producer.finding_type
        for producer in REGISTER.values()
        if producer.kind is Kind.REPORTABLE
    }

    assert declared == {INTERFERENCE_TYPE, FAULT_TYPE, "possible_data_source_issue"}


def test_the_timeline_carries_only_types_the_contract_can_name() -> None:
    """Spec: op-006 -- the timeline's `event` is the same vocabulary.

    `api-011` sends the finding type verbatim and the strip composes the copy,
    so an event carrying a type outside the union would reach the screen with
    no sentence available for it.
    """
    # spec: op-006, op-003, api-011
    picture = _scored([_fault()])
    nameable = set(union_members(_read(CONTRACT_PATHS), "ReportableFindingType"))

    assert picture.timelineEvents
    assert all(event.event in nameable for event in picture.timelineEvents)


def test_every_producer_the_endpoint_calls_persisted_is_registered() -> None:
    """Spec: api-012, anom-008.

    A pair misspelled here is not a loud failure: the key simply never matches a
    register entry, so a producer that does persist its findings is reported as
    *not persisted*, with its real count discarded. Nothing else notices --
    which is why the other half of this is asserted against `anom-015`'s own
    source in `test_anom_chain.py`.
    """
    # spec: api-012, anom-008
    assert PERSISTED_PRODUCERS <= set(REGISTER)
    assert all(REGISTER[key].built for key in PERSISTED_PRODUCERS)


# ------------------------------------- detection through the endpoint, live


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_a_run_the_pass_has_scored(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: api-012, anom-015, FR-904.

    The assembly is proved without a database above; this is the wiring, and the
    wiring is where `api-002`'s own reads were put behind a repository function
    so `db-006` had a real route to assert over. Four reads and no SQL here.
    """
    # spec: api-012, anom-015, db-006
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, [_observation()])
    factory = sessionmaker(bind=picture_database, autoflush=False)
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=FAULT_RULE,
        findings=[_fault()],
        policy={"RF-NOISE.threshold_db": "6.0"},
    )
    record_detection_pass(factory, RUN_ID, policy={"RF-NOISE.threshold_db": "6.0"})

    payload = _get(picture_database, monkeypatch)

    assert payload["detectionSummary"] is not None
    assert len(payload["detectionSummary"]["counts"]) == len(REGISTER)
    assert [event["event"] for event in payload["timelineEvents"]] == [FAULT_TYPE]
    assert len(payload["rfSensors"]) == len(LAYOUT.sensors)
    health = {sensor["id"]: sensor["health"] for sensor in payload["rfSensors"]}
    assert health[RECEIVER] == "fault"


@pytest.mark.database
@requires_database
def test_the_endpoint_reports_an_unscored_run_as_unscored(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: api-012, anom-008.

    The same database, the same run, the same observations -- and no pass. This
    is the pair the item's sharpest constraint is about, and the pair nothing in
    the store could distinguish before `anom-015` stamped the run.
    """
    # spec: api-012, anom-008, anom-015
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, [_observation()])

    payload = _get(picture_database, monkeypatch)

    assert payload["detectionSummary"] is None
    assert payload["timelineEvents"] == []
    assert {sensor["health"] for sensor in payload["rfSensors"]} == {"unknown"}


def test_a_finding_naming_a_receiver_outside_the_layout_is_refused() -> None:
    """Spec: api-012, scn-005.

    The findings and the layout have to be the same layout. Dropped silently,
    the receiver a rule named faulty is absent from the strip while the seven
    served read nominal -- a reassurance nothing checked, on a run where
    something was checked and found broken. Loud is the right failure here
    because the only way to reach it is serving findings produced against a
    different configuration, which no correct pass does.
    """
    # spec: api-012, scn-005
    with pytest.raises(PictureError, match="RF-99"):
        _scored([_fault("RF-99")])


def test_a_layout_whose_channels_span_two_bands_is_refused() -> None:
    """Spec: api-012, scn-005.

    The contract carries one band per receiver and the layout carries a channel
    plan, so the two agree only while that plan is one band -- which the shipped
    layout is. Taking the first channel's band would label every receiver with
    it, which on a two-band layout is silently wrong for whichever receivers
    watch the other, in the field an analyst reads to know what is monitored.
    """
    # spec: api-012, scn-005
    channels = (
        LAYOUT.channels[0],
        LAYOUT.channels[1].model_copy(update={"band": "GNSS-L5"}),
    )
    split = LAYOUT.model_copy(update={"channels": channels})

    with pytest.raises(PictureError, match="GNSS-L5"):
        build_operational_picture(
            layout=split, run=_run(), observations=[_observation()]
        )


# ------------------------------------------------------- the state of a track
#
# Spec: api-016. A receiver has carried the state the pass found it in since
# `api-012`; an aircraft carried a position and nothing else, so `op-004`'s
# *Tracks (n interrupted)* tab and `api-007`'s anomalous filter had no property
# to read. Three states, following `_receiver_health`: `interrupted` is a track
# `anom-010` raised a continuity gap for, `nominal` is one this run's findings
# say nothing about, and `unknown` is every track on a run no pass examined.

AIRCRAFT = "AC-48089ab4e5a9"
OTHER_AIRCRAFT = "AC-3c6444b1e2f0"
TRACK_STATES = {"nominal", "interrupted", "unknown"}


def _states(picture: OperationalPicture) -> dict[str, str]:
    return {track.name: track.state for track in picture.aircraftTracks}


def _two_aircraft() -> list[CanonicalObservation]:
    return [
        _observation(aircraft_id=AIRCRAFT),
        _observation(aircraft_id=OTHER_AIRCRAFT, lat=LAT + 0.5),
    ]


def test_the_track_state_is_one_closed_set_on_both_sides() -> None:
    """Spec: api-016.

    Three words and not a boolean. A `degraded` flag collapses *examined and
    clean* into *not examined*, which is the distinction `detectionSummary`'s
    nullability exists to carry -- so the set is compared against its
    declaration on both sides, as the other unions are.
    """
    # spec: api-016, api-002
    declared = set(union_members(_read(CONTRACT_PATHS), "TrackState"))
    field = AircraftTrack.model_json_schema()["properties"]["state"]

    assert declared == TRACK_STATES
    assert set(field.get("enum", ())) == TRACK_STATES
    assert _interfaces(_read(CONTRACT_PATHS))["AircraftTrack"]["state"] == "TrackState"


def test_every_track_on_an_unexamined_run_is_unknown() -> None:
    """Spec: api-016 -- the named failure case.

    A run no pass has examined must not report its aircraft nominal: that is a
    claim nothing established, the same one `_receiver_health` refuses for a
    receiver. A stored gap does not change it, because without a pass stamp
    the store cannot say the findings it holds are this run's whole account.
    """
    # spec: api-016, api-012
    picture = build_operational_picture(
        layout=LAYOUT,
        run=_run(),
        observations=_two_aircraft(),
        findings=[_gap(AIRCRAFT)],
    )

    assert _states(picture) == {AIRCRAFT: "unknown", OTHER_AIRCRAFT: "unknown"}


def test_every_track_on_a_quiet_examined_run_is_nominal() -> None:
    # spec: api-016, anom-008 -- examined and clean is a reading, not a default.
    picture = _scored([], observations=_two_aircraft())

    assert _states(picture) == {AIRCRAFT: "nominal", OTHER_AIRCRAFT: "nominal"}


def test_a_track_with_a_continuity_gap_is_interrupted() -> None:
    # spec: api-016, anom-010
    picture = _scored([_gap(AIRCRAFT)], observations=_two_aircraft())

    assert _states(picture) == {AIRCRAFT: "interrupted", OTHER_AIRCRAFT: "nominal"}


def test_a_track_with_several_gaps_is_interrupted_once() -> None:
    """Spec: api-016 -- the state is a state and not a count.

    Run 420 holds 17 gaps; an aircraft broken three times is one interrupted
    track, served once, and not three rows or a number.
    """
    # spec: api-016
    picture = _scored(
        [_gap(AIRCRAFT), _gap(AIRCRAFT), _gap(AIRCRAFT)], observations=_two_aircraft()
    )

    assert [t.name for t in picture.aircraftTracks].count(AIRCRAFT) == 1
    assert _states(picture)[AIRCRAFT] == "interrupted"


def test_an_interrupted_track_is_not_promoted_to_a_reported_anomaly() -> None:
    """Spec: api-016 -- a continuity gap stays intermediate.

    A quiet hour holds about 138 of them. The state says *this aircraft's
    reporting broke*, which is a fact about a track, and never *an anomaly was
    reported*, which is the ladder's to say: the summary's levels, its
    reportable counts and the timeline are what they were without the gap.
    """
    # spec: api-016, api-012, anom-010
    clean = _scored([], observations=_two_aircraft())
    gapped = _scored([_gap(AIRCRAFT)], observations=_two_aircraft())
    assert clean.detectionSummary is not None
    assert gapped.detectionSummary is not None

    assert _states(gapped)[AIRCRAFT] == "interrupted"
    assert gapped.detectionSummary.anomalyLevel == clean.detectionSummary.anomalyLevel
    assert (
        gapped.detectionSummary.signalIntegrity
        == clean.detectionSummary.signalIntegrity
    )
    assert gapped.timelineEvents == clean.timelineEvents == []
    assert _count_for(gapped, (GAP_RULE, GAP_TYPE)).kind == "intermediate"


def test_the_state_is_read_from_stored_findings_and_not_re_detected() -> None:
    """Spec: api-016 -- a join, not a detector (`anom-016`).

    The served observation looks exactly like a frozen position: its last fresh
    fix is two minutes old while the aircraft is still heard. A request that
    re-ran `anom-010` would call it interrupted; with no stored finding it is
    nominal, because the pass does not fire per request. The schema module
    takes the gap rule's two names and nothing else from it.
    """
    # spec: api-016, anom-016, anom-010
    frozen = _observation(aircraft_id=AIRCRAFT)
    assert isinstance(frozen.payload, TrackPayload)
    frozen = frozen.model_copy(
        update={
            "payload": frozen.payload.model_copy(
                update={"position_staleness_s": 120.0, "contact_staleness_s": 0.0}
            )
        }
    )

    assert _states(_scored([], observations=[frozen])) == {AIRCRAFT: "nominal"}

    taken = {
        alias.name
        for node in ast.walk(ast.parse(Path(picture_module.__file__).read_text()))
        if isinstance(node, ast.ImportFrom) and node.module == "app.detection.track_gap"
        for alias in node.names
    }
    assert taken == {"RULE_ID", "FINDING_TYPE"}


def test_the_join_is_on_the_pseudonym_as_stored() -> None:
    """Spec: api-016, NFR-405.

    `anom-010` keys a gap on the substituted identifier the observation
    carries, so the match needs no lookup and nothing reverses it. A finding
    keyed on anything else -- a resolved transponder address, or the track's
    own composite id -- names no served aircraft and marks none.
    """
    # spec: api-016, NFR-405, dal-004
    picture = _scored(
        [_gap("48089a"), _gap(f"opensky-replay:{AIRCRAFT}")],
        observations=_two_aircraft(),
    )

    assert _states(picture) == {AIRCRAFT: "nominal", OTHER_AIRCRAFT: "nominal"}

    assert "pseudonymise" not in Path(picture_module.__file__).read_text()


def test_a_gap_for_an_aircraft_not_on_screen_is_not_refused() -> None:
    """Spec: api-016.

    Unlike a receiver outside the layout, this is ordinary: a gap can fall
    anywhere in the hour, and the picture serves only the final window's
    positions. The aircraft has left; the served ones keep their own state.
    """
    # spec: api-016, api-002
    picture = _scored([_gap("AC-000000000000")], observations=_two_aircraft())

    assert _states(picture) == {AIRCRAFT: "nominal", OTHER_AIRCRAFT: "nominal"}


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_each_track_with_its_state(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-016 -- on the wire, from the stored gap and the run's stamp.
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, _two_aircraft())
    factory = sessionmaker(bind=picture_database, autoflush=False)
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=GAP_RULE,
        findings=[_gap(AIRCRAFT)],
        policy={"TRACK-GAP.threshold_s": "60"},
    )
    record_detection_pass(factory, RUN_ID, policy={"TRACK-GAP.threshold_s": "60"})

    tracks = _get(picture_database, monkeypatch)["aircraftTracks"]

    assert {t["name"]: t["state"] for t in tracks} == {
        AIRCRAFT: "interrupted",
        OTHER_AIRCRAFT: "nominal",
    }


# ------------------------------------------------------------- the view filter
#
# Spec: api-007. The screen asks for a view -- anomalous, nominal or all -- and
# the server sends only the rows that view admits, with the count it withheld
# per collection and whether the hour was examined at all. Filtered where the
# payload is assembled, over the same state each row is served with: a second
# definition of *interrupted* in SQL is a definition that can drift.

VIEWS = ("anomalous", "nominal", "all")
COLLECTIONS = ("rfSensors", "aircraftTracks", "timelineEvents", "interferenceZones")


def _viewed(
    view: str | None,
    findings: Sequence[DetectionFinding] = (),
    *,
    scored: bool = True,
) -> OperationalPicture:
    """A picture of two aircraft and the shipped layout, under one view."""
    kwargs: dict[str, Any] = {
        "layout": LAYOUT,
        "run": _run(),
        "observations": _two_aircraft(),
        "findings": findings,
    }
    if scored:
        kwargs["detection_pass"] = _detection_pass()
    if view is not None:
        kwargs["view"] = view
    return build_operational_picture(**kwargs)


def _mixed() -> list[DetectionFinding]:
    """One faulted receiver (a reportable claim, so one event) and one gap."""
    return [_fault(RECEIVER), _gap(AIRCRAFT)]


def _suppressed(picture: OperationalPicture) -> dict[str, int]:
    return picture.model_dump()["view"]["suppressed"]


def test_the_view_metadata_is_one_shape_on_both_sides() -> None:
    """Spec: api-007 -- declared in both halves of the contract.

    The two new interfaces are checked field for field in both directions, as
    every other interface is, and the selection is one closed set.
    """
    # spec: api-007, api-002
    source = _read(CONTRACT_PATHS)
    declared = _interfaces(source)
    view_model = getattr(picture_module, "PictureView", None)
    counts_model = getattr(picture_module, "SuppressedCounts", None)
    assert view_model is not None and counts_model is not None

    assert declared["OperationalPicture"]["view"] == "PictureView"
    assert set(declared["PictureView"]) == _model_fields(view_model)
    assert set(declared["SuppressedCounts"]) == _model_fields(counts_model)
    assert set(declared["SuppressedCounts"]) == set(COLLECTIONS)
    assert set(union_members(source, "ViewSelection")) == set(VIEWS)
    selected = view_model.model_json_schema()["properties"]["selected"]
    assert set(selected.get("enum", ())) == set(VIEWS)


def test_anomalous_admits_only_the_rows_a_finding_put_out_of_nominal() -> None:
    # spec: api-007, api-016, api-012
    picture = _viewed("anomalous", _mixed())

    assert [s.id for s in picture.rfSensors] == [RECEIVER]
    assert _states(picture) == {AIRCRAFT: "interrupted"}
    assert len(picture.timelineEvents) == 1
    assert _suppressed(picture) == {
        "rfSensors": len(LAYOUT.sensors) - 1,
        "aircraftTracks": 1,
        "timelineEvents": 0,
        "interferenceZones": 0,
    }


def test_nominal_admits_only_nominal_rows_and_no_event() -> None:
    # spec: api-007 -- a timeline event is a reportable claim by construction.
    picture = _viewed("nominal", _mixed())

    assert {s.health for s in picture.rfSensors} == {"nominal"}
    assert len(picture.rfSensors) == len(LAYOUT.sensors) - 1
    assert _states(picture) == {OTHER_AIRCRAFT: "nominal"}
    assert picture.timelineEvents == []
    assert _suppressed(picture) == {
        "rfSensors": 1,
        "aircraftTracks": 1,
        "timelineEvents": 1,
        "interferenceZones": 0,
    }


def test_all_admits_everything_and_withholds_nothing() -> None:
    # spec: api-007
    picture = _viewed("all", _mixed())

    assert len(picture.rfSensors) == len(LAYOUT.sensors)
    assert len(picture.aircraftTracks) == 2
    assert len(picture.timelineEvents) == 1
    assert _suppressed(picture) == dict.fromkeys(COLLECTIONS, 0)
    assert picture.model_dump()["view"]["selected"] == "all"


def test_an_absent_view_is_all_and_not_anomalous() -> None:
    """Spec: api-007 -- the named failure case of the amendment.

    Every request today carries no view. Filtering it as *anomalous* would empty
    the receiver strip on every quiet hour before any control exists to say
    why; the *Anomalous only* default belongs to the control that sends it.
    """
    # spec: api-007, op-007
    absent = _viewed(None, _mixed())

    assert absent == _viewed("all", _mixed())
    assert absent.model_dump()["view"]["selected"] == "all"


@pytest.mark.parametrize("view", VIEWS)
def test_shown_and_withheld_rows_account_for_the_whole_hour(view: str) -> None:
    """Spec: api-007, op-004 -- the footer's number is the rows that did not arrive.

    Per collection, what is served plus what was withheld is what `all` serves:
    a count that drifted from that would make *+n nominal hidden* untrue.
    """
    # spec: api-007, op-004
    everything = _viewed("all", _mixed()).model_dump()
    picture = _viewed(view, _mixed())
    served = picture.model_dump()

    for collection in COLLECTIONS:
        assert len(served[collection]) + _suppressed(picture)[collection] == len(
            everything[collection]
        ), collection


@pytest.mark.parametrize("view", ("anomalous", "nominal"))
def test_an_unexamined_hour_admits_nothing_but_all(view: str) -> None:
    """Spec: api-007, api-016 -- an `unknown` row is neither anomalous nor nominal.

    On a run no pass has examined every receiver and every track is `unknown`,
    so both narrow views are empty -- and the metadata says the hour was not
    examined, so 7 and 2 withheld cannot be read as an hour found clean.
    """
    # spec: api-007, api-016, api-012
    picture = _viewed(view, [_gap(AIRCRAFT)], scored=False)
    meta = picture.model_dump()["view"]

    assert picture.rfSensors == [] and picture.aircraftTracks == []
    assert meta["examined"] is False
    assert meta["suppressed"]["rfSensors"] == len(LAYOUT.sensors)
    assert meta["suppressed"]["aircraftTracks"] == 2


def test_an_unexamined_hour_under_all_serves_every_unknown_row() -> None:
    # spec: api-007, api-016
    picture = _viewed("all", scored=False)

    assert {s.health for s in picture.rfSensors} == {"unknown"}
    assert set(_states(picture).values()) == {"unknown"}
    assert _suppressed(picture) == dict.fromkeys(COLLECTIONS, 0)


@pytest.mark.parametrize("scored", (True, False))
def test_examined_is_exactly_whether_a_summary_is_served(scored: bool) -> None:
    # spec: api-007, api-012 -- one fact, carried twice, must never disagree.
    picture = _viewed("anomalous", _mixed(), scored=scored)

    assert picture.model_dump()["view"]["examined"] is (
        picture.detectionSummary is not None
    )
    assert picture.model_dump()["view"]["examined"] is scored


def test_the_detection_summary_is_the_whole_hour_whatever_the_view() -> None:
    # spec: api-007 -- a summary whose counts shrink with the view is a failure.
    summaries = {view: _viewed(view, _mixed()).detectionSummary for view in VIEWS}

    assert summaries["anomalous"] == summaries["nominal"] == summaries["all"]
    assert summaries["all"] is not None


def test_the_filter_is_not_written_a_second_time_in_sql() -> None:
    """Spec: api-007 -- the state has one definition, where the payload is built.

    The persistence layer may not name a track state or a receiver state: a
    predicate there would be a second definition of what the builder decides.
    """
    # spec: api-007, api-016
    db_sources = Path(picture_module.__file__).resolve().parents[3] / "db"
    named = {
        path.name
        for path in db_sources.glob("*.py")
        for word in ('"interrupted"', '"deviating"', '"anomalous"')
        if word in path.read_text()
    }

    assert named == set()
    assert "view" in build_operational_picture.__code__.co_varnames


def _get_with(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, **params: str
) -> tuple[int, dict[str, Any]]:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        response = client.get("/api/v1/operational-picture", params=params)
    return response.status_code, dict(response.json())


@pytest.mark.database
@requires_database
@pytest.mark.parametrize("value", ("everything", "Anomalous", ""))
def test_an_unrecognised_view_is_refused_rather_than_read_as_all(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    # spec: api-007 -- the original failure case; case is not forgiven either.
    status, _ = _get_with(picture_database, monkeypatch, view=value)

    assert status == 422


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_the_selected_view_with_its_metadata(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-007, api-016 -- on the wire, from the stored gap and the stamp.
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, _two_aircraft())
    factory = sessionmaker(bind=picture_database, autoflush=False)
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=GAP_RULE,
        findings=[_gap(AIRCRAFT)],
        policy={"TRACK-GAP.threshold_s": "60"},
    )
    record_detection_pass(factory, RUN_ID, policy={"TRACK-GAP.threshold_s": "60"})

    status, anomalous = _get_with(picture_database, monkeypatch, view="anomalous")
    _, absent = _get_with(picture_database, monkeypatch)

    assert status == 200
    assert [t["name"] for t in anomalous["aircraftTracks"]] == [AIRCRAFT]
    assert anomalous["rfSensors"] == []
    assert anomalous["view"] == {
        "selected": "anomalous",
        "examined": True,
        "suppressed": {
            "rfSensors": len(LAYOUT.sensors),
            "aircraftTracks": 1,
            "timelineEvents": 0,
            "interferenceZones": 0,
        },
    }
    assert absent["view"]["selected"] == "all"
    assert len(absent["aircraftTracks"]) == 2


# ------------------------------------------------- interference zones, api-017
#
# The most important conclusion the system reaches -- interference over an
# area -- had no place on the map, because the picture carried it as a line in
# the timeline and nothing more. Each stored claim now travels with its centre,
# its receivers, its window, its confidence, its corroboration and the radius
# the aircraft side was measured over. The system never estimates how far
# interference reaches, so the radius is the one the claim was judged under,
# read from the settings stored with it, and absent when none was stored.

#: The setting stored with a finding that names the radius anom-012 measured over.
RADIUS_KEY = "FUSION-SPATIAL.excess_radius_km"


def _claim(
    *sensors: str,
    offset_s: int = 0,
    confidence: str = "medium",
    corroboration: str = "not_measurable",
) -> DetectionFinding:
    return _finding(
        rule_id=FUSION_RULE,
        finding_type=INTERFERENCE_TYPE,
        subject=sensors[0],
        offset_s=offset_s,
        details={
            "confidence": confidence,
            "sensors": list(sensors),
            "corroboration": corroboration,
        },
    )


def _id_of(finding: DetectionFinding) -> str:
    return f"{finding.rule_id}:{finding.subject}:{finding.started_at.isoformat()}"


def _zones(picture: OperationalPicture) -> list[dict[str, Any]]:
    return list(picture.model_dump()["interferenceZones"])


def test_an_interference_claim_becomes_one_zone_joined_to_its_conclusion() -> None:
    # spec: api-017
    claim = _claim(RECEIVER, OTHER_RECEIVER)
    picture = _scored([claim], zone_radii={_id_of(claim): 60.0})

    (zone,) = _zones(picture)
    assert zone == {
        "id": picture.timelineEvents[0].id,
        "centre": {"lat": LAT, "lon": LON},
        "radiusKm": 60.0,
        "receivers": [RECEIVER, OTHER_RECEIVER],
        "startedAt": claim.started_at.isoformat(),
        "endedAt": claim.ended_at.isoformat(),
        "confidence": "Medium",
        "corroboration": "not_measurable",
    }


def test_a_radius_the_store_did_not_record_is_served_as_absent() -> None:
    # spec: api-017 -- the named failure case: a code default of 60.
    (zone,) = _zones(_scored([_claim(RECEIVER, OTHER_RECEIVER)]))

    assert zone["radiusKm"] is None


def test_the_radius_is_the_one_recorded_with_the_claim() -> None:
    # spec: api-017 -- never the detector's current setting.
    claim = _claim(RECEIVER, OTHER_RECEIVER)

    (zone,) = _zones(_scored([claim], zone_radii={_id_of(claim): 45.0}))

    assert zone["radiusKm"] == 45.0


def test_only_interference_claims_become_zones() -> None:
    # spec: api-017 -- a sensor fault is a receiver, and no intermediate is a zone.
    claim = _claim(RECEIVER, OTHER_RECEIVER, offset_s=60)

    zones = _zones(_scored([_fault(OTHER_RECEIVER), _rf(), _gap(), claim]))

    assert [zone["id"] for zone in zones] == [_id_of(claim)]


def test_zones_are_ordered_like_their_conclusions() -> None:
    # spec: api-017, op-006
    later = _claim(OTHER_RECEIVER, RECEIVER, offset_s=600)
    earlier = _claim(RECEIVER, OTHER_RECEIVER, offset_s=60)

    picture = _scored([later, earlier])

    assert [zone["id"] for zone in _zones(picture)] == [
        event.id for event in picture.timelineEvents
    ]


@pytest.mark.parametrize(
    ("view", "served", "withheld"),
    (("anomalous", 1, 0), ("nominal", 0, 1), ("all", 1, 0)),
)
def test_zones_are_filtered_like_the_conclusions(
    view: str, served: int, withheld: int
) -> None:
    # spec: api-017 (3), api-007 -- the named failure case: a zone under nominal.
    picture = _viewed(view, [_claim(RECEIVER, OTHER_RECEIVER)])

    assert len(_zones(picture)) == served
    assert _suppressed(picture)["interferenceZones"] == withheld


def test_an_unexamined_run_serves_no_zones() -> None:
    # spec: api-017 (3)
    picture = _viewed("all", scored=False)

    assert _zones(picture) == []
    assert picture.view.examined is False


def test_the_confidence_is_a_level_and_not_a_number() -> None:
    # spec: api-017 -- the named failure case, and the project-wide rule.
    (zone,) = _zones(_scored([_claim(RECEIVER, OTHER_RECEIVER, confidence="high")]))

    assert zone["confidence"] == "High"
    with pytest.raises(PictureError):
        _scored([_claim(RECEIVER, OTHER_RECEIVER, confidence="0.8")])


def test_the_corroboration_is_served_verbatim_for_the_screen_to_word() -> None:
    # spec: api-017 -- facts, never prose (op-003).
    claim = _claim(RECEIVER, OTHER_RECEIVER, corroboration="corroborated")

    (zone,) = _zones(_scored([claim]))

    assert zone["corroboration"] == "corroborated"


@pytest.mark.database
@requires_database
def test_the_store_returns_the_radius_recorded_with_each_interference_claim(
    picture_database: Engine,
) -> None:
    # spec: api-017 (2) -- read from the settings stored with the finding.
    from app.db.findings import interference_radii_for_run

    _insert_run(picture_database, RUN_ID, completed=True)
    factory = sessionmaker(bind=picture_database, autoflush=False)
    claim = _claim(RECEIVER, OTHER_RECEIVER)
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=FUSION_RULE,
        findings=[claim],
        policy={RADIUS_KEY: "60.0"},
    )
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=FAULT_RULE,
        findings=[_fault(OTHER_RECEIVER)],
        policy={RADIUS_KEY: "60.0"},
    )

    assert interference_radii_for_run(factory, RUN_ID) == {_id_of(claim): 60.0}


@pytest.mark.database
@requires_database
def test_the_store_returns_no_radius_for_a_claim_stored_without_settings(
    picture_database: Engine,
) -> None:
    # spec: api-017 -- unprovenanced is absent, never defaulted.
    from app.db.findings import interference_radii_for_run

    _insert_run(picture_database, RUN_ID, completed=True)
    factory = sessionmaker(bind=picture_database, autoflush=False)
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=FUSION_RULE,
        findings=[_claim(RECEIVER, OTHER_RECEIVER)],
    )

    assert interference_radii_for_run(factory, RUN_ID) == {}


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_each_zone_with_its_recorded_radius(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-017 -- on the wire, from the stored claim, its settings and the stamp.
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(picture_database, _two_aircraft())
    factory = sessionmaker(bind=picture_database, autoflush=False)
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=FUSION_RULE,
        findings=[_claim(RECEIVER, OTHER_RECEIVER)],
        policy={RADIUS_KEY: "60.0"},
    )
    record_detection_pass(factory, RUN_ID, policy={RADIUS_KEY: "60.0"})

    _, anomalous = _get_with(picture_database, monkeypatch, view="anomalous")
    _, nominal = _get_with(picture_database, monkeypatch, view="nominal")

    (zone,) = anomalous["interferenceZones"]
    assert zone["radiusKm"] == 60.0
    assert zone["id"] == anomalous["timelineEvents"][0]["id"]
    assert zone["receivers"] == [RECEIVER, OTHER_RECEIVER]
    assert nominal["interferenceZones"] == []
    assert nominal["view"]["suppressed"]["interferenceZones"] == 1
