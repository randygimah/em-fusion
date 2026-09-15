"""The proximity query. Spec: db-004.

FR-905 asks for one real PostGIS spatial query and names this one: track
discontinuities within N km of an RF anomaly zone. It is the justification
for the spatial database, so the tests below are less about whether a
filter works than about *which* filter -- a query that answered in degrees
would return plausible rows forever.

Three groups. **Distance** is the group that matters, and its central case
is built so that a degree-based answer and a metre-based one disagree: at
52 degrees north half a degree of longitude is about 34 km while half a
degree of latitude is about 56 km, so a radius applied to raw coordinates
is wrong by a different factor in each direction. **Window** fixes what
"inside that window" means for a finding that is itself an interval, which
the item did not say and which overlap-versus-containment answers
differently. **Scope** holds the line that every metric in `eval-002` is
computed per run.

The findings this reads are `db-008`'s, not `anomalies`: that table wants a
severity, a Polygon and a bundle link, and an intermediate finding has
none of the three.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import Location
from app.db.findings import findings_near, save_findings
from app.db.migrations import alembic_config
from app.detection.findings import DetectionFinding
from tests.conftest import requires_database

RUN_ID = 1
OTHER_RUN_ID = 2

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
#: The window every window test is measured against.
WINDOW = (START + timedelta(seconds=100), START + timedelta(seconds=300))

#: A point in the middle of the corpus box, and three neighbours. The two
#: half-degree offsets are the pair that separates a metre answer from a
#: degree one: east is about 34 km away, north about 56, and a radius of 45
#: km therefore admits one and excludes the other -- while any rule applied
#: to the raw coordinates treats both as the same 0.5 and excludes both.
CENTRE = Location(lat=52.0, lon=5.0)
EAST = Location(lat=52.0, lon=5.5)
NORTH = Location(lat=52.5, lon=5.0)
FAR = Location(lat=53.0, lon=5.0)

RADIUS_KM = 45.0


def finding(
    *,
    subject: str,
    location: Location,
    started_at: datetime = START + timedelta(seconds=150),
    ended_at: datetime = START + timedelta(seconds=200),
    scenario_run_id: int = RUN_ID,
    rule_id: str = "TRACK-GAP",
) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=rule_id,
        finding_type="track_continuity_gap",
        subject=subject,
        started_at=started_at,
        ended_at=ended_at,
        location=location,
        evidence_refs=({"aircraft_id": subject},),
        details={"shape": "not_heard"},
    )


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", empty_database.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")

    with empty_database.connect() as connection:
        for run_id, scenario in ((RUN_ID, "gnss-degradation"), (OTHER_RUN_ID, "normal-baseline")):
            connection.execute(
                text(
                    "INSERT INTO scenario_runs "
                    "(id, scenario_type, parameters, seed, started_at) "
                    "VALUES (:id, :scenario, '{}'::jsonb, 42, now())"
                ),
                {"id": run_id, "scenario": scenario},
            )
        connection.commit()
    return empty_database


@pytest.fixture
def factory(migrated_database: Engine) -> sessionmaker:
    return sessionmaker(bind=migrated_database, autoflush=False)


def store(factory: sessionmaker, *findings: DetectionFinding) -> None:
    by_rule: dict[tuple[int, str], list[DetectionFinding]] = {}
    for f in findings:
        by_rule.setdefault((f.scenario_run_id, f.rule_id), []).append(f)
    for (run_id, rule_id), group in by_rule.items():
        save_findings(factory, scenario_run_id=run_id, rule_id=rule_id, findings=group)


def near(factory: sessionmaker, **kwargs: object) -> list[DetectionFinding]:
    call: dict[str, object] = {
        "scenario_run_id": RUN_ID,
        "centre": CENTRE,
        "radius_km": RADIUS_KM,
        "window": WINDOW,
    }
    call.update(kwargs)
    return findings_near(factory, **call)  # type: ignore[arg-type]


# ----------------------------------------------------------------- distance


@pytest.mark.database
@requires_database
def test_a_finding_inside_the_radius_is_returned(factory: sessionmaker) -> None:
    # spec: db-004, FR-905
    store(factory, finding(subject="near", location=EAST))

    assert [f.subject for f in near(factory)] == ["near"]


@pytest.mark.database
@requires_database
def test_a_finding_outside_the_radius_is_excluded(factory: sessionmaker) -> None:
    """The item's named failure case: just outside must be outside."""
    # spec: db-004
    store(factory, finding(subject="far", location=FAR))

    assert near(factory) == []


@pytest.mark.database
@requires_database
def test_distance_is_measured_in_metres_and_not_in_degrees(
    factory: sessionmaker,
) -> None:
    """The test this item exists for.

    Both points are half a degree from the centre. East is about 34 km away
    and north about 56, because a degree of longitude shortens with the
    cosine of latitude while a degree of latitude does not. A query that
    compared raw coordinates would treat the two as equally distant and
    exclude both; one measuring on geography admits exactly one.
    """
    # spec: db-004, FR-905
    store(
        factory,
        finding(subject="east-34km", location=EAST),
        finding(subject="north-56km", location=NORTH),
    )

    assert [f.subject for f in near(factory)] == ["east-34km"]


@pytest.mark.database
@requires_database
def test_a_finding_exactly_at_the_radius_is_inside_it(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """`ST_DWithin` is inclusive, and the item's original failure case fixed
    only the far side of the boundary. The exact distance is asked of
    PostGIS rather than computed here, so the test cannot disagree with the
    query about what the distance is."""
    # spec: db-004
    with migrated_database.connect() as connection:
        metres = connection.execute(
            text(
                "SELECT ST_Distance("
                "  ST_GeomFromEWKT('SRID=4326;POINT(5.0 52.0)')::geography,"
                "  ST_GeomFromEWKT('SRID=4326;POINT(5.5 52.0)')::geography)"
            )
        ).scalar_one()
    store(factory, finding(subject="on-the-line", location=EAST))

    assert [f.subject for f in near(factory, radius_km=metres / 1000.0)] == [
        "on-the-line"
    ]


@pytest.mark.database
@requires_database
def test_the_radius_is_a_parameter_and_not_a_constant(factory: sessionmaker) -> None:
    # spec: db-004
    store(factory, finding(subject="north-56km", location=NORTH))

    assert near(factory, radius_km=45.0) == []
    assert [f.subject for f in near(factory, radius_km=80.0)] == ["north-56km"]


@pytest.mark.database
@requires_database
def test_the_query_can_use_the_spatial_index(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """`db-001` created a GiST index for this query and `db-008` carried it
    to the table the findings actually live in. An index the query cannot
    use is the defect that survives every other test in this file, because
    the answers stay correct and only the plan changes.

    Sequential scans are disabled for the plan so the question is whether
    the index *can* be used, not whether the planner prefers it on a table
    holding three rows.
    """
    # spec: db-004, db-008, db-001
    store(factory, finding(subject="near", location=EAST))

    with migrated_database.connect() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in connection.execute(
                text(
                    "EXPLAIN SELECT id FROM detection_findings "
                    "WHERE scenario_run_id = 1 AND ST_DWithin("
                    "  location::geography,"
                    "  ST_GeomFromEWKT('SRID=4326;POINT(5.0 52.0)')::geography,"
                    "  45000)"
                )
            )
        )

    assert "Index Scan" in plan or "Bitmap Index Scan" in plan, plan
    assert "location" in plan, plan


# ------------------------------------------------------------------- window


@pytest.mark.database
@requires_database
def test_a_finding_wholly_inside_the_window_is_returned(
    factory: sessionmaker,
) -> None:
    # spec: db-004
    store(factory, finding(subject="inside", location=EAST))

    assert [f.subject for f in near(factory)] == ["inside"]


@pytest.mark.database
@requires_database
def test_a_finding_overlapping_either_edge_is_returned(
    factory: sessionmaker,
) -> None:
    """Overlap, not containment. `anom-005` fuses an RF deviation with a
    track gap in the same window, and a gap that began before the window
    opened is still happening during it -- requiring containment would drop
    exactly the long disruptions the fusion rule is looking for."""
    # spec: db-004, anom-005
    store(
        factory,
        finding(
            subject="straddles-start",
            location=EAST,
            started_at=START + timedelta(seconds=50),
            ended_at=START + timedelta(seconds=150),
        ),
        finding(
            subject="straddles-end",
            location=EAST,
            started_at=START + timedelta(seconds=250),
            ended_at=START + timedelta(seconds=400),
        ),
    )

    assert {f.subject for f in near(factory)} == {"straddles-start", "straddles-end"}


@pytest.mark.database
@requires_database
def test_a_finding_spanning_the_whole_window_is_returned(
    factory: sessionmaker,
) -> None:
    # spec: db-004
    store(
        factory,
        finding(
            subject="spans",
            location=EAST,
            started_at=START,
            ended_at=START + timedelta(seconds=600),
        ),
    )

    assert [f.subject for f in near(factory)] == ["spans"]


@pytest.mark.database
@requires_database
def test_findings_entirely_outside_the_window_are_excluded(
    factory: sessionmaker,
) -> None:
    # spec: db-004
    store(
        factory,
        finding(
            subject="before",
            location=EAST,
            started_at=START,
            ended_at=START + timedelta(seconds=50),
        ),
        finding(
            subject="after",
            location=EAST,
            started_at=START + timedelta(seconds=400),
            ended_at=START + timedelta(seconds=500),
        ),
    )

    assert near(factory) == []


# -------------------------------------------------------------------- scope


@pytest.mark.database
@requires_database
def test_findings_from_another_run_are_never_returned(
    factory: sessionmaker,
) -> None:
    """Same place, same window, different run. Every metric in `eval-002`
    is per run, so a query reaching across them would fuse evidence from two
    separately staged incidents and report it as one."""
    # spec: db-004, eval-002
    store(
        factory,
        finding(subject="mine", location=EAST),
        finding(subject="theirs", location=EAST, scenario_run_id=OTHER_RUN_ID),
    )

    assert [f.subject for f in near(factory)] == ["mine"]


@pytest.mark.database
@requires_database
def test_one_rule_can_be_asked_for(factory: sessionmaker) -> None:
    """`anom-005` wants track gaps near an RF zone, not everything near it."""
    # spec: db-004, anom-005
    store(
        factory,
        finding(subject="gap", location=EAST),
        finding(subject="rf", location=EAST, rule_id="RF-NOISE"),
    )

    assert [f.subject for f in near(factory, rule_id="TRACK-GAP")] == ["gap"]


@pytest.mark.database
@requires_database
def test_nothing_nearby_returns_an_empty_list(factory: sessionmaker) -> None:
    """The item's second named failure case: a list, not a null, not an
    error. An empty answer is the ordinary case on a quiet run."""
    # spec: db-004
    assert near(factory) == []


@pytest.mark.database
@requires_database
def test_what_comes_back_is_the_model_that_went_in(factory: sessionmaker) -> None:
    # spec: db-004, db-008
    written = finding(subject="near", location=EAST)
    store(factory, written)

    assert near(factory) == [written]


@pytest.mark.database
@requires_database
def test_the_order_is_deterministic(factory: sessionmaker) -> None:
    """A run must be reproducible from its seed, and a result set whose
    order depends on how the database happened to return rows is not."""
    # spec: db-004, NFR-601
    store(
        factory,
        finding(
            subject="second",
            location=EAST,
            started_at=START + timedelta(seconds=200),
            ended_at=START + timedelta(seconds=250),
        ),
        finding(
            subject="first",
            location=EAST,
            started_at=START + timedelta(seconds=120),
            ended_at=START + timedelta(seconds=160),
        ),
    )

    assert [f.subject for f in near(factory)] == ["first", "second"]
