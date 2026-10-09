"""Receiver states over an hour, for playback. Spec: api-018.

The picture gives each receiver one state for the whole hour: the worst any
stored finding put it in. Playback (`op-008`, `map-004`) moves through the hour,
so a receiver faulted for two minutes would read faulted from the first second
to the last. This endpoint serves each receiver's timeline instead -- the
intervals in which stored findings put it out of nominal -- for `map-007` to
draw at the cursor.

Three kinds of test, the playback split.

**Contract parity.** The three shapes are declared in the TypeScript contract
and as response models; both directions are compared, and the state union is
compared against the picture's own ladder.

**Assembly**, over a pure builder taking a run, the layout, the stored findings
and the pass stamp. All the judgement lives there: which finding puts which
receiver in which state, what wins where two overlap, and what an unexamined
hour may claim. The ladder is the picture's, so the agreement test runs both
builders over the same findings.

**The endpoint against a live database**, marked and skipped without one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.schemas.operational_picture import (
    RECEIVER_STATES,
    PictureError,
    build_operational_picture,
)
from app.dal.models import Location
from app.db.findings import save_findings
from app.db.repository import record_detection_pass
from app.detection.findings import DetectionFinding
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE_TYPE
from app.detection.fusion import RULE_ID as FUSION_RULE
from app.detection.rf_noise import ANOMALY_TYPE as RF_TYPE
from app.detection.rf_noise import RULE_ID as RF_RULE
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT_TYPE
from app.detection.sensor_fault import RULE_ID as FAULT_RULE
from app.detection.track_gap import FINDING_TYPE as GAP_TYPE
from app.detection.track_gap import RULE_ID as GAP_RULE
from app.main import app
from tests.conftest import requires_database
from tests.contracts import contract_paths, union_members
from tests.contracts import interfaces as _interfaces
from tests.contracts import read_contract as _read
from tests.test_api_operational_picture import (  # noqa: F401 -- a fixture
    HOUR_START,
    LAT,
    LAYOUT,
    OTHER_RECEIVER,
    RECEIVER,
    RUN_ID,
    _detection_pass,
    _insert_run,
    _observation,
    _run,
    picture_database,
)


def _states() -> Any:
    """The module under test, imported late so a missing module fails each test
    rather than the whole file at collection."""
    from app.api.v1.schemas import receiver_states

    return receiver_states


CONTRACT_PATHS = contract_paths("operationalPicture.ts")

SHAPES = ("ReceiverStates", "ReceiverTimeline", "ReceiverStateInterval")

#: A third receiver, for findings that must touch neither of the other two.
THIRD_RECEIVER = LAYOUT.sensors[2].sensor_id


def _at(offset_s: int) -> datetime:
    return HOUR_START + timedelta(seconds=offset_s)


def _finding(
    rule_id: str,
    finding_type: str,
    subject: str,
    start_s: int,
    end_s: int,
    details: dict[str, Any] | None = None,
    *,
    run_id: int = RUN_ID,
) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=run_id,
        rule_id=rule_id,
        finding_type=finding_type,
        subject=subject,
        started_at=_at(start_s),
        ended_at=_at(end_s),
        location=Location(lat=LAT, lon=7.5),
        details=details or {},
    )


def _fault(receiver: str, start_s: int, end_s: int, **kwargs: Any) -> DetectionFinding:
    return _finding(
        FAULT_RULE,
        FAULT_TYPE,
        receiver,
        start_s,
        end_s,
        {"confidence": "high"},
        **kwargs,
    )


def _rf(
    receiver: str, start_s: int, end_s: int, *, channel: int = 0
) -> DetectionFinding:
    return _finding(
        RF_RULE,
        RF_TYPE,
        f"{receiver}:{channel}",
        start_s,
        end_s,
        {"severity": "high", "metric": "power_dbm"},
    )


def _zone(start_s: int, end_s: int, *receivers: str) -> DetectionFinding:
    return _finding(
        FUSION_RULE,
        INTERFERENCE_TYPE,
        receivers[0],
        start_s,
        end_s,
        {
            "confidence": "medium",
            "sensors": list(receivers),
            "corroboration": "not_measurable",
        },
    )


def _built(findings: Sequence[DetectionFinding] = (), *, scored: bool = True) -> Any:
    return _states().build_receiver_states(
        run=_run(),
        layout=LAYOUT,
        findings=findings,
        detection_pass=_detection_pass() if scored else None,
    )


def _intervals(states: Any, receiver: str) -> list[tuple[str, int, int]]:
    """One receiver's intervals as (state, start, end) in seconds into the hour."""
    [timeline] = [r for r in states.receivers if r.id == receiver]
    return [
        (
            interval.state,
            int((interval.startedAt - HOUR_START).total_seconds()),
            int((interval.endedAt - HOUR_START).total_seconds()),
        )
        for interval in timeline.intervals
    ]


# --------------------------------------------------------------- contract parity


@pytest.mark.parametrize("name", SHAPES)
def test_each_receiver_state_shape_and_its_model_carry_the_same_fields(
    name: str,
) -> None:
    # spec: api-018 -- declared once per language, compared in both directions.
    declared = _interfaces(_read(CONTRACT_PATHS))
    model = getattr(_states(), name)

    assert name in declared
    assert set(declared[name]) == set(
        model.model_json_schema(by_alias=True)["properties"]
    )


def test_the_contracts_interval_states_are_the_pictures_ladder() -> None:
    # spec: api-018 -- the words an interval may carry are exactly those the
    # picture's ladder puts a receiver in, declared once on each side.
    declared = union_members(_read(CONTRACT_PATHS), "ReceiverOutOfNominal")

    assert set(declared) == {state for _key, state in RECEIVER_STATES}


# --------------------------------------------------------------------- assembly


def test_every_receiver_in_the_layout_is_served_in_layout_order() -> None:
    # spec: api-018 -- per receiver in the layout (scn-005), clean or not.
    states = _built([_fault(RECEIVER, 0, 60)])

    assert [r.id for r in states.receivers] == [s.sensor_id for s in LAYOUT.sensors]


def test_an_examined_hour_with_nothing_found_serves_empty_intervals() -> None:
    # spec: api-018 -- examined and clean is an empty list per receiver.
    states = _built()

    assert states.examined is True
    assert {len(r.intervals) for r in states.receivers} == {0}


def test_an_unexamined_hour_serves_null_rather_than_empty_intervals() -> None:
    # spec: api-018 -- the named failure case: empty would read as always
    # nominal (api-012's distinction). Findings handed over without a pass stamp
    # are not served either; the stamp is what says anybody looked.
    states = _built([_fault(RECEIVER, 0, 60)], scored=False)

    assert states.examined is False
    assert {r.intervals is None for r in states.receivers} == {True}


def test_the_run_is_named() -> None:
    # spec: api-018 -- so the screen can refuse an answer for another hour.
    assert _built().runId == RUN_ID


def test_a_sensor_fault_puts_its_receiver_in_fault_over_its_window() -> None:
    # spec: api-018, anom-007
    states = _built([_fault(RECEIVER, 120, 240)])

    assert _intervals(states, RECEIVER) == [("fault", 120, 240)]
    assert _intervals(states, OTHER_RECEIVER) == []


def test_a_radio_deviation_on_a_channel_puts_its_receiver_deviating() -> None:
    # spec: api-018, anom-001 -- the subject is a receiver and channel cell.
    states = _built([_rf(RECEIVER, 60, 180, channel=3)])

    assert _intervals(states, RECEIVER) == [("deviating", 60, 180)]


def test_an_interference_claim_puts_every_receiver_it_names_deviating() -> None:
    # spec: api-018, anom-005, api-017 -- a zone names its receivers in its
    # details; filed under the first, it is about all of them, and it blames
    # none, so it is never a fault.
    states = _built([_zone(100, 400, RECEIVER, OTHER_RECEIVER)])

    assert _intervals(states, RECEIVER) == [("deviating", 100, 400)]
    assert _intervals(states, OTHER_RECEIVER) == [("deviating", 100, 400)]
    assert _intervals(states, THIRD_RECEIVER) == []


def test_findings_of_other_rules_put_no_receiver_out_of_nominal() -> None:
    # spec: api-018 -- a continuity gap is about an aircraft, not a receiver.
    states = _built([_finding(GAP_RULE, GAP_TYPE, "AC-48089ab4e5a9", 0, 300)])

    assert {len(r.intervals) for r in states.receivers} == {0}


def test_a_fault_inside_a_deviation_wins_for_its_window_only() -> None:
    # spec: api-018 -- the worst state wins where intervals overlap, and only
    # there: the deviation either side of the fault is still served.
    states = _built([_rf(RECEIVER, 0, 300), _fault(RECEIVER, 100, 200)])

    assert _intervals(states, RECEIVER) == [
        ("deviating", 0, 100),
        ("fault", 100, 200),
        ("deviating", 200, 300),
    ]


def test_a_deviation_inside_a_fault_is_not_served() -> None:
    # spec: api-018 -- the failure case: deviating where the fault, and so the
    # picture's whole-hour state, says fault for the same moment.
    states = _built([_fault(RECEIVER, 0, 300), _zone(100, 200, RECEIVER)])

    assert _intervals(states, RECEIVER) == [("fault", 0, 300)]


def test_a_deviation_overlapping_a_faults_end_resumes_after_it() -> None:
    # spec: api-018
    states = _built([_fault(RECEIVER, 0, 150), _rf(RECEIVER, 100, 300)])

    assert _intervals(states, RECEIVER) == [
        ("fault", 0, 150),
        ("deviating", 150, 300),
    ]


def test_overlapping_and_touching_intervals_in_one_state_are_served_as_one() -> None:
    # spec: api-018 -- two channels deviating together, and a claim taking over
    # where they stop, are one deviating stretch of the receiver.
    states = _built(
        [
            _rf(RECEIVER, 0, 300, channel=0),
            _rf(RECEIVER, 200, 500, channel=1),
            _zone(500, 600, RECEIVER),
        ]
    )

    assert _intervals(states, RECEIVER) == [("deviating", 0, 600)]


def test_a_stretch_no_finding_covers_is_left_nominal() -> None:
    # spec: api-018 -- the failure case: an interval invented outside a stored
    # finding's window, here by joining two findings across the gap between them.
    states = _built([_rf(RECEIVER, 0, 100), _rf(RECEIVER, 400, 500, channel=2)])

    assert _intervals(states, RECEIVER) == [
        ("deviating", 0, 100),
        ("deviating", 400, 500),
    ]


def test_intervals_are_served_oldest_first_whatever_order_they_were_stored_in() -> None:
    # spec: api-018
    states = _built([_fault(RECEIVER, 600, 700), _rf(RECEIVER, 0, 100)])

    assert _intervals(states, RECEIVER) == [
        ("deviating", 0, 100),
        ("fault", 600, 700),
    ]


def test_an_instantaneous_finding_is_served_and_not_lost() -> None:
    # spec: api-018 -- a finding whose window is one instant still put the
    # receiver out of nominal at that instant; a sweep over half-open stretches
    # would drop it without a word.
    states = _built([_fault(RECEIVER, 300, 300)])

    assert _intervals(states, RECEIVER) == [("fault", 300, 300)]


#: An hour with every kind of overlap on several receivers at once.
MIXED = (
    _rf(RECEIVER, 0, 300),
    _fault(RECEIVER, 100, 200),
    _zone(250, 600, RECEIVER, OTHER_RECEIVER),
    _rf(OTHER_RECEIVER, 700, 800, channel=4),
    _fault(THIRD_RECEIVER, 50, 60),
    _rf(THIRD_RECEIVER, 0, 500, channel=1),
)


def test_each_receivers_worst_interval_is_the_pictures_whole_hour_state() -> None:
    # spec: api-018, api-012 -- the two answers cannot disagree about what the
    # worst moment was: the same findings through both builders.
    rank = {"fault": 2, "deviating": 1}
    picture = build_operational_picture(
        run=_run(),
        observations=[_observation()],
        layout=LAYOUT,
        findings=MIXED,
        detection_pass=_detection_pass(),
    )
    states = _built(MIXED)

    worst = {
        timeline.id: max(
            (interval.state for interval in timeline.intervals),
            key=rank.__getitem__,
            default="nominal",
        )
        for timeline in states.receivers
    }
    assert worst == {sensor.id: sensor.health for sensor in picture.rfSensors}


def test_every_interval_lies_inside_its_receivers_stored_findings() -> None:
    # spec: api-018 -- the failure case: an interval invented outside a stored
    # finding's window. Every moment served out of nominal, the bounds and the
    # middle of each interval, is inside some finding naming that receiver.
    windows: dict[str, list[tuple[int, int]]] = {
        RECEIVER: [(0, 300), (100, 200), (250, 600)],
        OTHER_RECEIVER: [(250, 600), (700, 800)],
        THIRD_RECEIVER: [(50, 60), (0, 500)],
    }
    states = _built(MIXED)

    for receiver, spans in windows.items():
        for _state, start, end in _intervals(states, receiver):
            for moment in (start, (start + end) / 2, end):
                assert any(s <= moment <= e for s, e in spans), (receiver, moment)
    assert _intervals(states, OTHER_RECEIVER) == [
        ("deviating", 250, 600),
        ("deviating", 700, 800),
    ]


def test_a_finding_naming_a_receiver_outside_the_layout_is_refused() -> None:
    # spec: api-018 -- the picture's refusal, for the picture's reason: served,
    # it would show the named receiver nowhere while a rule had named it.
    with pytest.raises(PictureError):
        _built([_fault("RX-NOT-IN-LAYOUT", 0, 60)])


# ------------------------------------------------------------------ the endpoint


def _get_states(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, **params: str
) -> tuple[int, Any]:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/operational-picture/receiver-states", params=params
        )
    return response.status_code, response.json()


def _seed(engine: Engine, *, examined: bool = True) -> None:
    """Run 1 with a fault on one receiver inside a deviation, and run 2 with a
    fault on another receiver, which must never leak in."""
    _insert_run(engine, RUN_ID, completed=True)
    _insert_run(engine, 2, completed=True, started_offset_s=1)
    factory = sessionmaker(bind=engine, autoflush=False)
    policy = {"SENSOR-FAULT.min_s": "10"}
    stored = {
        RUN_ID: {
            FAULT_RULE: [_fault(RECEIVER, 100, 200)],
            RF_RULE: [_rf(RECEIVER, 0, 300)],
        },
        2: {FAULT_RULE: [_fault(OTHER_RECEIVER, 0, 60, run_id=2)]},
    }
    for run_id, by_rule in stored.items():
        for rule_id, findings in by_rule.items():
            save_findings(
                factory,
                scenario_run_id=run_id,
                rule_id=rule_id,
                findings=findings,
                policy=policy,
            )
        if examined or run_id == 2:
            record_detection_pass(factory, run_id, policy=policy)


def _seconds(body: dict[str, Any], receiver: str) -> list[tuple[str, int, int]]:
    [timeline] = [r for r in body["receivers"] if r["id"] == receiver]
    return [
        (
            interval["state"],
            int(
                (
                    datetime.fromisoformat(interval["startedAt"]) - HOUR_START
                ).total_seconds()
            ),
            int(
                (
                    datetime.fromisoformat(interval["endedAt"]) - HOUR_START
                ).total_seconds()
            ),
        )
        for interval in timeline["intervals"]
    ]


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_the_stored_findings_of_the_run_asked_for(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-018, db-006 -- a join on stored findings and the run's stamp.
    _seed(picture_database)

    status, body = _get_states(picture_database, monkeypatch, run=str(RUN_ID))

    assert status == 200
    assert body["runId"] == RUN_ID
    assert body["examined"] is True
    assert _seconds(body, RECEIVER) == [
        ("deviating", 0, 100),
        ("fault", 100, 200),
        ("deviating", 200, 300),
    ]
    # Run 2's fault on this receiver is not run 1's.
    assert _seconds(body, OTHER_RECEIVER) == []


@pytest.mark.database
@requires_database
def test_the_endpoint_filters_by_nothing(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-018 -- the receivers' timeline, not a view: every receiver,
    # clean ones included, whatever view the screen is showing.
    _seed(picture_database)

    _, body = _get_states(
        picture_database, monkeypatch, run=str(RUN_ID), view="anomalous"
    )

    assert [r["id"] for r in body["receivers"]] == [s.sensor_id for s in LAYOUT.sensors]


@pytest.mark.database
@requires_database
def test_an_unexamined_run_serves_null_intervals(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-018 -- findings in the store without the run's stamp are not an
    # examined hour.
    _seed(picture_database, examined=False)

    _, body = _get_states(picture_database, monkeypatch, run=str(RUN_ID))

    assert body["examined"] is False
    assert {r["intervals"] is None for r in body["receivers"]} == {True}


@pytest.mark.database
@requires_database
def test_an_unknown_run_is_a_404_naming_it(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-018, api-013 -- never another run's states. The detail is
    # asserted because a route that does not exist is also a 404.
    _seed(picture_database)

    status, body = _get_states(picture_database, monkeypatch, run="999")

    assert status == 404
    assert "999" in str(body["detail"])


@pytest.mark.database
@requires_database
def test_the_run_is_required(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-018 -- playback is of one hour; there is no "newest" timeline.
    # The body is asserted because a missing route answers 404, not 422.
    _seed(picture_database)

    status, body = _get_states(picture_database, monkeypatch)

    assert status == 422
    assert any(error["loc"][-1] == "run" for error in body["detail"])
