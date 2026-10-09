"""The time-windowed track query for playback. Spec: api-008.

Playback (`op-008`, `map-004`) needs every aircraft's positions across a run,
not where each was last seen. A run is fifteen simulated minutes, about 33,000
positions from about 520 aircraft at a ten-second cadence -- about 3 MB as JSON
-- so the screen asks for one span at a time and buffers ahead of its cursor
(FR-718, FR-810), and the server bounds the span.

Four kinds of test, the picture's split.

**Contract parity.** The four shapes are declared in the TypeScript contract
and as response models; both directions are compared.

**Assembly**, over a pure builder taking a run, the observations already read,
the stored findings and the pass stamp. All the judgement lives there: the
order within an aircraft, the naming, the unit, the view, the gaps and what an
unexamined hour may claim.

**The span**, checked before anything is read: at most 300 s, the picture's own
final window, refused with 422 rather than cut short, so an answer is never
partial.

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

from app.api.v1.schemas.operational_picture import build_operational_picture
from app.dal.models import CanonicalObservation, Location
from app.db.findings import save_findings
from app.db.repository import record_detection_pass
from app.detection.findings import DetectionFinding
from app.detection.rf_noise import ANOMALY_TYPE as RF_TYPE
from app.detection.rf_noise import RULE_ID as RF_RULE
from app.detection.track_gap import FINDING_TYPE as GAP_TYPE
from app.detection.track_gap import RULE_ID as GAP_RULE
from app.main import app
from tests.conftest import requires_database
from tests.contracts import contract_paths
from tests.contracts import interfaces as _interfaces
from tests.contracts import read_contract as _read
from tests.test_api_operational_picture import (  # noqa: F401 -- a fixture
    AIRCRAFT,
    ALTITUDE_FT,
    HOUR_START,
    LAT,
    LAYOUT,
    OTHER_AIRCRAFT,
    RUN_ID,
    _detection_pass,
    _insert_run,
    _observation,
    _run,
    _save,
    picture_database,
)


def _playback() -> Any:
    """The module under test, imported late so a missing module fails each test
    rather than the whole file at collection."""
    from app.api.v1.schemas import playback

    return playback


CONTRACT_PATHS = contract_paths("operationalPicture.ts")

SHAPES = ("PlaybackWindow", "PlaybackAircraft", "PlaybackPosition", "PlaybackGap")

#: The span used throughout: the first two minutes of the run.
SPAN_START = HOUR_START
SPAN_END = HOUR_START + timedelta(seconds=120)


def _at(offset_s: int) -> datetime:
    return HOUR_START + timedelta(seconds=offset_s)


def _track_gap(
    aircraft: str, start_s: int, end_s: int, *, rule_id: str = GAP_RULE
) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=RUN_ID,
        rule_id=rule_id,
        finding_type=GAP_TYPE if rule_id == GAP_RULE else RF_TYPE,
        subject=aircraft,
        started_at=_at(start_s),
        ended_at=_at(end_s),
        location=Location(lat=LAT, lon=7.5),
        details={},
    )


def _positions(
    aircraft: str, *offsets: int, **kwargs: Any
) -> list[CanonicalObservation]:
    return [_observation(aircraft_id=aircraft, offset_s=s, **kwargs) for s in offsets]


def _two_aircraft_moving() -> list[CanonicalObservation]:
    """Two aircraft, three reports each, handed over newest first and interleaved."""
    return [
        *_positions(AIRCRAFT, 20, 0, 10),
        *_positions(OTHER_AIRCRAFT, 10, 20, 0, lat=LAT + 0.5),
    ]


def _built(
    observations: Sequence[CanonicalObservation] | None = None,
    findings: Sequence[DetectionFinding] = (),
    *,
    scored: bool = True,
    view: str | None = None,
    recorded: tuple[datetime, datetime] | None = (_at(0), _at(890)),
    start: datetime = SPAN_START,
    end: datetime = SPAN_END,
) -> Any:
    kwargs: dict[str, Any] = {
        "run": _run(),
        "observations": (
            _two_aircraft_moving() if observations is None else observations
        ),
        "recorded": recorded,
        "start": start,
        "end": end,
        "findings": findings,
        "detection_pass": _detection_pass() if scored else None,
    }
    if view is not None:
        kwargs["view"] = view
    return _playback().build_playback_window(**kwargs)


def _by_name(window: Any) -> dict[str, Any]:
    return {aircraft.name: aircraft for aircraft in window.aircraft}


# --------------------------------------------------------------- contract parity


@pytest.mark.parametrize("name", SHAPES)
def test_each_playback_shape_and_its_model_carry_the_same_fields(name: str) -> None:
    # spec: api-008 -- declared once per language, compared in both directions.
    declared = _interfaces(_read(CONTRACT_PATHS))
    model = getattr(_playback(), name)

    assert name in declared
    assert set(declared[name]) == set(
        model.model_json_schema(by_alias=True)["properties"]
    )


# --------------------------------------------------------------------- assembly


def test_positions_are_served_oldest_first_within_each_aircraft() -> None:
    # spec: api-008 -- the failure case: out of order within an aircraft, so the
    # client would interpolate backwards in time.
    window = _built()

    for aircraft in window.aircraft:
        times = [position.time for position in aircraft.positions]
        assert times == sorted(times)
        assert len(times) == 3


def test_each_aircraft_is_named_exactly_as_the_picture_names_it() -> None:
    # spec: api-008 -- so a playback track and a picture track join on id.
    observations = _two_aircraft_moving()
    picture = build_operational_picture(
        run=_run(), observations=observations, layout=LAYOUT
    )

    window = _built(observations)

    assert {(a.id, a.name) for a in window.aircraft} == {
        (track.id, track.name) for track in picture.aircraftTracks
    }


def test_altitude_is_served_in_feet_and_an_absent_one_as_null() -> None:
    # spec: api-008 -- the picture's unit, and no altitude invented.
    window = _built(
        [
            _observation(aircraft_id=AIRCRAFT, offset_s=0),
            _observation(aircraft_id=AIRCRAFT, offset_s=10, altitude_m=None),
        ]
    )

    altitudes = [p.altitudeFt for p in _by_name(window)[AIRCRAFT].positions]
    assert altitudes == [ALTITUDE_FT, None]


def test_the_served_window_is_the_span_asked_for_and_the_recorded_one_beside_it() -> (
    None
):
    # spec: api-008 -- the run's own window, so the client knows where playback ends.
    window = _built(recorded=(_at(0), _at(890)))

    assert (window.servedFrom, window.servedTo) == (SPAN_START, SPAN_END)
    assert (window.recordedFrom, window.recordedTo) == (_at(0), _at(890))
    assert window.runId == RUN_ID


def test_a_run_with_no_positions_has_no_recorded_window() -> None:
    # spec: api-008 -- null, not an invented hour.
    window = _built([], recorded=None)

    assert (window.recordedFrom, window.recordedTo) == (None, None)
    assert window.aircraft == []


def test_a_gap_overlapping_the_span_is_served_with_its_aircraft() -> None:
    # spec: api-008 -- the stored gap, so a broken segment can be drawn (map-004).
    window = _built(findings=[_track_gap(AIRCRAFT, 60, 180)])

    gaps = _by_name(window)[AIRCRAFT].gaps
    assert [(g.startedAt, g.endedAt) for g in gaps] == [(_at(60), _at(180))]


def test_a_gap_outside_the_span_is_not_served() -> None:
    # spec: api-008
    window = _built(findings=[_track_gap(AIRCRAFT, 400, 500)])

    assert _by_name(window)[AIRCRAFT].gaps == []


def test_an_examined_aircraft_with_no_gap_has_an_empty_list() -> None:
    # spec: api-008 -- empty means looked and found none.
    window = _built(findings=[_track_gap(AIRCRAFT, 60, 180)])

    assert _by_name(window)[OTHER_AIRCRAFT].gaps == []


def test_gaps_are_served_oldest_first() -> None:
    # spec: api-008
    window = _built(
        findings=[_track_gap(AIRCRAFT, 90, 100), _track_gap(AIRCRAFT, 5, 30)]
    )

    starts = [g.startedAt for g in _by_name(window)[AIRCRAFT].gaps]
    assert starts == [_at(5), _at(90)]


def test_an_unexamined_hour_serves_no_gap_list_at_all() -> None:
    # spec: api-008 -- the failure case: an empty list on an unexamined hour
    # reads as "no gaps found", which nobody looked for.
    window = _built(scored=False)

    assert window.examined is False
    assert {a.name: a.gaps for a in window.aircraft} == {
        AIRCRAFT: None,
        OTHER_AIRCRAFT: None,
    }


def test_gaps_are_read_from_stored_findings_and_not_re_detected() -> None:
    # spec: api-008, api-016 -- a two-minute hole in the reports, and no stored
    # gap: nothing is served, because the builder is a join and not a detector.
    window = _built(_positions(AIRCRAFT, 0, 120, 130), findings=[])

    assert _by_name(window)[AIRCRAFT].gaps == []


def test_only_continuity_gaps_become_gaps() -> None:
    # spec: api-008 -- another rule's finding naming the aircraft is not a gap.
    window = _built(findings=[_track_gap(AIRCRAFT, 60, 180, rule_id=RF_RULE)])

    assert _by_name(window)[AIRCRAFT].gaps == []


def test_each_aircraft_carries_the_state_the_picture_gives_it() -> None:
    # spec: api-008, api-016 -- one definition of interrupted.
    window = _built(findings=[_track_gap(AIRCRAFT, 60, 180)])

    assert {a.name: a.state for a in window.aircraft} == {
        AIRCRAFT: "interrupted",
        OTHER_AIRCRAFT: "nominal",
    }


# ------------------------------------------------------------------- the view


def test_anomalous_serves_only_interrupted_aircraft_and_counts_the_rest() -> None:
    # spec: api-008, api-007 -- so pressing play under Anomalous only does not
    # fill the map with every aircraft.
    window = _built(findings=[_track_gap(AIRCRAFT, 60, 180)], view="anomalous")

    assert [a.name for a in window.aircraft] == [AIRCRAFT]
    assert window.withheld == 1
    assert window.view == "anomalous"


def test_nominal_serves_only_nominal_aircraft() -> None:
    # spec: api-008, api-007
    window = _built(findings=[_track_gap(AIRCRAFT, 60, 180)], view="nominal")

    assert [a.name for a in window.aircraft] == [OTHER_AIRCRAFT]
    assert window.withheld == 1


def test_an_absent_view_is_all() -> None:
    # spec: api-008, api-007 -- absent is all, as on the picture.
    window = _built(findings=[_track_gap(AIRCRAFT, 60, 180)])

    assert window.view == "all"
    assert window.withheld == 0
    assert len(window.aircraft) == 2


def test_an_unexamined_hour_admits_no_aircraft_but_under_all() -> None:
    # spec: api-008, api-007 -- nothing on it is anomalous or nominal yet.
    assert _built(scored=False, view="anomalous").aircraft == []
    assert _built(scored=False, view="nominal").withheld == 2
    assert {a.state for a in _built(scored=False, view="all").aircraft} == {"unknown"}


# ------------------------------------------------------------------- the span


def test_the_bound_is_the_pictures_own_final_window() -> None:
    # spec: api-008 -- 300 s, about 1 MB of positions under All.
    from app.api.v1.operational_picture import FINAL_WINDOW_SECONDS

    assert _playback().MAX_SPAN_SECONDS == FINAL_WINDOW_SECONDS == 300


def test_a_span_at_the_bound_is_accepted() -> None:
    # spec: api-008
    _playback().check_span(_at(0), _at(300))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (_at(0), _at(301)),  # over the bound
        (_at(60), _at(60)),  # empty
        (_at(60), _at(0)),  # backwards
    ],
)
def test_a_span_over_the_bound_or_not_forwards_is_refused(
    start: datetime, end: datetime
) -> None:
    # spec: api-008 -- refused, never cut short.
    playback = _playback()
    with pytest.raises(playback.PlaybackError):
        playback.check_span(start, end)


def test_a_span_without_a_timezone_is_refused() -> None:
    # spec: api-008 -- simulated time is UTC; a naive time is a guess at an hour.
    playback = _playback()
    with pytest.raises(playback.PlaybackError):
        playback.check_span(datetime(2022, 6, 27, 12, 0), datetime(2022, 6, 27, 12, 1))


def test_the_refusal_names_the_bound() -> None:
    # spec: api-008 -- the client is told how far it may ask.
    playback = _playback()
    with pytest.raises(playback.PlaybackError, match="300"):
        playback.check_span(_at(0), _at(600))


# ------------------------------------------------------- against the database


def _get_tracks(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, **params: str
) -> tuple[int, Any]:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        response = client.get("/api/v1/operational-picture/tracks", params=params)
    return response.status_code, response.json()


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _span(start_s: int, end_s: int, **extra: str) -> dict[str, str]:
    return {
        "run": str(RUN_ID),
        "from": _iso(_at(start_s)),
        "to": _iso(_at(end_s)),
        **extra,
    }


def _seed(engine: Engine) -> None:
    """Run 1 with two aircraft reporting every ten seconds for four minutes, and
    run 2 with one aircraft at the same instants, which must never leak in."""
    _insert_run(engine, RUN_ID, completed=True)
    _insert_run(engine, 2, completed=True, started_offset_s=1)
    offsets = range(0, 240, 10)
    _save(
        engine,
        [
            *_positions(AIRCRAFT, *offsets),
            *_positions(OTHER_AIRCRAFT, *offsets, lat=LAT + 0.5),
            *_positions("AC-otherrun0000", *offsets, run_id=2),
        ],
    )


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_the_half_open_span_of_the_run_asked_for(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008, FR-810
    _seed(picture_database)

    status, body = _get_tracks(picture_database, monkeypatch, **_span(60, 120))

    assert status == 200
    names = {aircraft["name"] for aircraft in body["aircraft"]}
    assert names == {AIRCRAFT, OTHER_AIRCRAFT}
    for aircraft in body["aircraft"]:
        times = [p["time"] for p in aircraft["positions"]]
        assert times == sorted(times)
        # 60, 70, ..., 110: from included, to excluded.
        assert len(times) == 6


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_the_runs_recorded_window(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008 -- the first and last position the run holds.
    _seed(picture_database)

    _, body = _get_tracks(picture_database, monkeypatch, **_span(0, 60))

    assert datetime.fromisoformat(body["recordedFrom"]) == _at(0)
    assert datetime.fromisoformat(body["recordedTo"]) == _at(230)


@pytest.mark.database
@requires_database
def test_a_span_over_the_bound_is_refused_and_names_it(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008 -- the named failure case: never served in full, never cut short.
    _seed(picture_database)

    status, body = _get_tracks(picture_database, monkeypatch, **_span(0, 301))

    assert status == 422
    assert "300" in str(body["detail"])


@pytest.mark.database
@requires_database
def test_a_backwards_span_is_refused(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008
    _seed(picture_database)

    status, _ = _get_tracks(picture_database, monkeypatch, **_span(120, 60))

    assert status == 422


@pytest.mark.database
@requires_database
def test_a_span_wholly_outside_the_run_is_an_empty_list_and_not_an_error(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008 -- the named failure case.
    _seed(picture_database)

    status, body = _get_tracks(picture_database, monkeypatch, **_span(3600, 3700))

    assert status == 200
    assert body["aircraft"] == []


@pytest.mark.database
@requires_database
def test_a_span_partly_outside_the_run_serves_the_overlap(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008 -- 200..240 holds reports at 200, 210, 220, 230.
    _seed(picture_database)

    status, body = _get_tracks(picture_database, monkeypatch, **_span(200, 400))

    assert status == 200
    assert {len(a["positions"]) for a in body["aircraft"]} == {4}


@pytest.mark.database
@requires_database
def test_an_unknown_run_is_a_404(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008, api-013 -- never another run's tracks. The detail is
    # asserted too: a route that does not exist is also a 404, and that one
    # passed this test before the endpoint was written.
    _seed(picture_database)

    status, body = _get_tracks(
        picture_database, monkeypatch, **{**_span(0, 60), "run": "999"}
    )

    assert status == 404
    assert "999" in str(body["detail"])


@pytest.mark.database
@requires_database
def test_the_run_is_required(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008 -- playback is of one hour; there is no "newest" span.
    _seed(picture_database)
    params = _span(0, 60)
    del params["run"]

    status, _ = _get_tracks(picture_database, monkeypatch, **params)

    assert status == 422


@pytest.mark.database
@requires_database
@pytest.mark.parametrize("value", ("everything", "Anomalous"))
def test_an_unrecognised_view_is_refused(
    picture_database: Engine,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    # spec: api-008, api-007
    _seed(picture_database)

    status, _ = _get_tracks(picture_database, monkeypatch, **_span(0, 60, view=value))

    assert status == 422


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_stored_gaps_and_filters_by_view(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008, api-016, api-007 -- from the store and the run's stamp.
    _seed(picture_database)
    factory = sessionmaker(bind=picture_database, autoflush=False)
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=GAP_RULE,
        findings=[_track_gap(AIRCRAFT, 30, 90)],
        policy={"TRACK-GAP.threshold_s": "60"},
    )
    record_detection_pass(factory, RUN_ID, policy={"TRACK-GAP.threshold_s": "60"})

    _, body = _get_tracks(
        picture_database, monkeypatch, **_span(0, 120, view="anomalous")
    )

    assert body["examined"] is True
    assert body["withheld"] == 1
    [aircraft] = body["aircraft"]
    assert aircraft["name"] == AIRCRAFT
    assert aircraft["state"] == "interrupted"
    assert [
        (datetime.fromisoformat(g["startedAt"]), datetime.fromisoformat(g["endedAt"]))
        for g in aircraft["gaps"]
    ] == [(_at(30), _at(90))]


@pytest.mark.database
@requires_database
def test_an_unexamined_run_serves_null_gaps(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    # spec: api-008 -- no pass, so no gap list at all.
    _seed(picture_database)

    _, body = _get_tracks(picture_database, monkeypatch, **_span(0, 60))

    assert body["examined"] is False
    assert {a["gaps"] is None for a in body["aircraft"]} == {True}
