"""Grouping detection findings by proximity. Spec: db-009.

Its sibling `db-004` asks *what is near this one spot*. This asks *which of
these belong together*, and it is the step where a pile of intermediate
findings becomes an object with a place and a size. A single track gap is
not evidence -- a quiet run holds about 138 of them -- while twelve inside
five kilometres of each other, in the same few minutes, is. Nothing in the
system can say the second sentence until this query exists.

Five groups. **Grouping** is the item's own arithmetic, including the
transitive chaining it records as a limitation rather than a defect.
**Metres** is the group that matters, built so a degree-based answer and a
metre-based one give different *memberships* and not merely different
counts. **Shape** covers the centroid and the covering geometry, and holds
the line that a group of one has no area to claim. **Determinism** is
NFR-601 at this seam: a run is reproducible from its seed, so the same
findings must give the same groups in the same order however the rows come
back. **Scope** keeps the query inside one run and one rule.

Every distance in the comments below was measured against PostGIS 3.5 on
2026-09-15 rather than computed by hand, because the last two items in this
phase both found an assumption that the database did not share.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.dal.models import Location
from app.db.findings import cluster_findings, save_findings
from app.db.migrations import alembic_config
from app.detection.findings import DetectionFinding, FindingCluster
from tests.conftest import requires_database

RUN_ID = 1
OTHER_RUN_ID = 2
RULE = "TRACK-GAP"

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
WINDOW = (START + timedelta(seconds=100), START + timedelta(seconds=300))

#: Three points on one line of latitude, each 4.121 km from the next and
#: 8.241 km end to end. At a 5 km radius they are one group and the ends are
#: not within the radius of each other, which is the transitive property the
#: item records as a limitation. `LONE` is 68.677 km from A.
A = Location(lat=52.0, lon=5.00)
B = Location(lat=52.0, lon=5.06)
C = Location(lat=52.0, lon=5.12)
LONE = Location(lat=52.0, lon=6.00)

#: The pair that separates metres from degrees. Both are exactly half a
#: degree from the centre, and they are 34.339 km and 55.636 km away.
CENTRE = Location(lat=52.0, lon=5.0)
EAST = Location(lat=52.0, lon=5.5)
NORTH = Location(lat=52.5, lon=5.0)

CHAIN_RADIUS_KM = 5.0
WIDE_RADIUS_KM = 45.0


def finding(
    *,
    subject: str,
    location: Location,
    started_at: datetime = START + timedelta(seconds=150),
    ended_at: datetime = START + timedelta(seconds=200),
    scenario_run_id: int = RUN_ID,
    rule_id: str = RULE,
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
        for run_id, scenario in (
            (RUN_ID, "gnss-degradation"),
            (OTHER_RUN_ID, "normal-baseline"),
        ):
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


def clusters(factory: sessionmaker, **kwargs: object) -> list[FindingCluster]:
    call: dict[str, object] = {
        "scenario_run_id": RUN_ID,
        "rule_id": RULE,
        "radius_km": CHAIN_RADIUS_KM,
        "window": WINDOW,
    }
    call.update(kwargs)
    return cluster_findings(factory, **call)  # type: ignore[arg-type]


def subjects(groups: list[FindingCluster]) -> list[list[str]]:
    return [[f.subject for f in group.members] for group in groups]


# ----------------------------------------------------------------- grouping


@pytest.mark.database
@requires_database
def test_findings_within_the_radius_form_one_group(factory: sessionmaker) -> None:
    # spec: db-009, FR-305
    store(factory, finding(subject="a", location=A), finding(subject="b", location=B))

    assert subjects(clusters(factory)) == [["a", "b"]]


@pytest.mark.database
@requires_database
def test_findings_further_apart_than_the_radius_form_separate_groups(
    factory: sessionmaker,
) -> None:
    """The item's first named failure case. A and LONE are 68.677 km apart
    with nothing between them, at a radius of 5 km."""
    # spec: db-009
    store(
        factory,
        finding(subject="a", location=A),
        finding(subject="lone", location=LONE),
    )

    assert subjects(clusters(factory)) == [["a"], ["lone"]]


@pytest.mark.database
@requires_database
def test_a_chain_of_findings_forms_one_group_wider_than_the_radius(
    factory: sessionmaker,
) -> None:
    """The transitive property, asserted rather than discovered.

    A to B is 4.121 km and B to C is 4.121 km, both inside a 5 km radius,
    but A to C is 8.241 km and is not. All three are one group. That is the
    right answer for interference spreading outwards from a source and the
    wrong one for aircraft strung along a single airway, and the item
    records it as a limitation because the project has no basis yet for
    preferring either.
    """
    # spec: db-009
    store(
        factory,
        finding(subject="a", location=A),
        finding(subject="b", location=B),
        finding(subject="c", location=C),
    )

    assert subjects(clusters(factory)) == [["a", "b", "c"]]


@pytest.mark.database
@requires_database
def test_an_isolated_finding_is_a_group_of_one_and_not_dropped(
    factory: sessionmaker,
) -> None:
    """The item's second named failure case. It is tempting to discard a
    lone finding as noise, but `anom-006` needs to know a dropout happened
    alone -- a single source going quiet by itself is an infrastructure
    problem rather than an incident."""
    # spec: db-009, anom-006
    store(factory, finding(subject="lone", location=LONE))

    groups = clusters(factory)

    assert subjects(groups) == [["lone"]]
    assert groups[0].size == 1


@pytest.mark.database
@requires_database
def test_every_finding_belongs_to_exactly_one_group(factory: sessionmaker) -> None:
    """Not a tautology of the implementation: a query that recovered group
    membership by intersecting each finding against a cluster's geometry
    could place a point in two, and two findings at the same location are
    where that would show."""
    # spec: db-009
    store(
        factory,
        finding(subject="a", location=A),
        finding(subject="a-again", location=A),
        finding(subject="b", location=B),
        finding(subject="lone", location=LONE),
    )

    groups = clusters(factory)
    placed = [f.subject for group in groups for f in group.members]

    assert sorted(placed) == ["a", "a-again", "b", "lone"]
    assert len(placed) == len(set(placed))


@pytest.mark.database
@requires_database
def test_the_radius_is_a_parameter_and_not_a_constant(factory: sessionmaker) -> None:
    """The same three points, three answers. At 3 km nothing reaches its
    neighbour, because A to B is 4.121 km. At 5 km A and B close and LONE
    stays out at 64.557 km from B. At 70 km the chain reaches LONE as well.
    """
    # spec: db-009
    store(
        factory,
        finding(subject="a", location=A),
        finding(subject="b", location=B),
        finding(subject="lone", location=LONE),
    )

    assert subjects(clusters(factory, radius_km=3.0)) == [["a"], ["b"], ["lone"]]
    assert subjects(clusters(factory, radius_km=5.0)) == [["a", "b"], ["lone"]]
    assert subjects(clusters(factory, radius_km=70.0)) == [["a", "b", "lone"]]


# ------------------------------------------------------------------- metres


@pytest.mark.database
@requires_database
def test_the_radius_is_measured_in_metres_and_not_in_degrees(
    factory: sessionmaker,
) -> None:
    """The test this item exists for.

    EAST and NORTH are each exactly half a degree from CENTRE, and 34.339
    km and 55.636 km away -- a degree of longitude at 52 north is about 69
    km while a degree of latitude is about 111. A query clustering on raw
    coordinates sees one number, 0.5, for both, so at any threshold it puts
    all three points in one group or leaves all three apart. Measuring in
    metres at a 45 km radius gives neither: CENTRE joins EAST and NORTH
    stands alone.
    """
    # spec: db-009, db-004
    store(
        factory,
        finding(subject="centre", location=CENTRE),
        finding(subject="east-34km", location=EAST),
        finding(subject="north-56km", location=NORTH),
    )

    assert subjects(clusters(factory, radius_km=WIDE_RADIUS_KM)) == [
        ["centre", "east-34km"],
        ["north-56km"],
    ]


# -------------------------------------------------------------------- shape


@pytest.mark.database
@requires_database
def test_the_centroid_is_the_areal_centre_and_not_the_mean_of_degrees(
    factory: sessionmaker,
) -> None:
    """A centroid taken in degrees underweights longitude, because a degree
    of it is shorter than a degree of latitude. For these four findings the
    mean of the coordinates is POINT(5.1175 52.0125) and the areal centre is
    POINT(5.117447601845757 52.012561112115044); measured against PostGIS
    3.5, the two lie 7.69 m apart. Small, and free to get right, and the
    point an analyst is shown as the centre of the disruption.
    """
    # spec: db-009
    store(
        factory,
        finding(subject="w", location=Location(lat=52.0, lon=5.0)),
        finding(subject="x", location=Location(lat=52.1, lon=5.3)),
        finding(subject="y", location=Location(lat=51.9, lon=5.15)),
        finding(subject="z", location=Location(lat=52.05, lon=5.02)),
    )

    (group,) = clusters(factory, radius_km=WIDE_RADIUS_KM)

    assert group.centroid.lon == pytest.approx(5.117447601845757, abs=1e-7)
    assert group.centroid.lat == pytest.approx(52.012561112115044, abs=1e-7)
    assert group.centroid.lat != pytest.approx(52.0125, abs=1e-6)


@pytest.mark.database
@requires_database
def test_a_group_of_three_is_covered_by_a_polygon(factory: sessionmaker) -> None:
    # spec: db-009, FR-301
    store(
        factory,
        finding(subject="a", location=Location(lat=52.0, lon=5.00)),
        finding(subject="b", location=Location(lat=52.0, lon=5.06)),
        finding(subject="c", location=Location(lat=52.03, lon=5.03)),
    )

    (group,) = clusters(factory)

    assert group.hull_wkt.startswith("POLYGON")


@pytest.mark.database
@requires_database
def test_a_group_of_one_or_two_has_no_area_to_claim(factory: sessionmaker) -> None:
    """Recorded rather than papered over. A group of one was observed at a
    point and a group of two along a line; inventing a polygon for either
    would claim an extent nothing was seen across. Turning a cluster into a
    reportable anomaly, which needs a Polygon, is `anom-004`'s decision to
    make and not this query's to pre-empt.
    """
    # spec: db-009, anom-004
    store(
        factory,
        finding(subject="a", location=A),
        finding(subject="b", location=B),
        finding(subject="lone", location=LONE),
    )

    pair, lone = clusters(factory)

    assert pair.hull_wkt.startswith("LINESTRING")
    assert lone.hull_wkt.startswith("POINT")


@pytest.mark.database
@requires_database
def test_the_covering_geometry_keeps_the_coordinates_that_were_stored(
    factory: sessionmaker,
) -> None:
    """The vertices of a hull are findings that are already stored exactly,
    and a round trip through the metre projection does not return them
    unchanged -- longitude 5.0 comes back as 4.999999999999997. The radius
    is what needs metres; the shape does not, so the shape is not sent
    through the projection to get them.
    """
    # spec: db-009
    store(factory, finding(subject="lone", location=LONE))

    (group,) = clusters(factory)

    assert group.hull_wkt == "POINT(6 52)"


# ------------------------------------------------------------- determinism


@pytest.mark.database
@requires_database
def test_the_same_findings_give_the_same_groups_in_the_same_order(
    factory: sessionmaker,
) -> None:
    """NFR-601 at this seam. A run is reproducible from its seed, and a
    result that changed with the order rows came back from the database
    would break that without ever failing a membership assertion. The
    cluster ids PostGIS hands out are its own internal numbering over rows
    with no imposed order, so they are not the order used here.
    """
    # spec: db-009, NFR-601
    inserted = [
        finding(subject="a", location=A),
        finding(subject="b", location=B),
        finding(subject="lone", location=LONE),
    ]

    store(factory, *inserted)
    first = clusters(factory)

    store(factory, *reversed(inserted))
    second = clusters(factory)

    assert subjects(first) == subjects(second) == [["a", "b"], ["lone"]]
    assert first == second


@pytest.mark.database
@requires_database
def test_members_are_ordered_by_time_then_subject(factory: sessionmaker) -> None:
    """Within a group as well as between them. Two findings at the same
    instant order by subject, which is stable; a third that started earlier
    comes first whatever its subject."""
    # spec: db-009, NFR-601
    store(
        factory,
        finding(subject="zulu", location=A),
        finding(subject="alpha", location=B),
        finding(
            subject="whisky",
            location=A,
            started_at=START + timedelta(seconds=120),
            ended_at=START + timedelta(seconds=140),
        ),
    )

    assert subjects(clusters(factory)) == [["whisky", "alpha", "zulu"]]


@pytest.mark.database
@requires_database
def test_groups_are_ordered_by_their_first_member(factory: sessionmaker) -> None:
    """The later group is stored first, so an answer that followed insertion
    order or the database's cluster numbering would return them the other
    way round."""
    # spec: db-009, NFR-601
    store(
        factory,
        finding(
            subject="later",
            location=LONE,
            started_at=START + timedelta(seconds=250),
            ended_at=START + timedelta(seconds=290),
        ),
        finding(
            subject="earlier",
            location=A,
            started_at=START + timedelta(seconds=110),
            ended_at=START + timedelta(seconds=150),
        ),
    )

    assert subjects(clusters(factory)) == [["earlier"], ["later"]]


# -------------------------------------------------------------------- scope


@pytest.mark.database
@requires_database
def test_findings_from_another_run_are_never_grouped_in(
    factory: sessionmaker,
) -> None:
    """Same place, same window, different run. Every metric in `eval-002` is
    computed per run, and a cluster spanning two separately staged incidents
    would report them as one."""
    # spec: db-009, eval-002
    store(
        factory,
        finding(subject="mine", location=A),
        finding(subject="theirs", location=B, scenario_run_id=OTHER_RUN_ID),
    )

    assert subjects(clusters(factory)) == [["mine"]]


@pytest.mark.database
@requires_database
def test_findings_from_another_rule_are_never_grouped_in(
    factory: sessionmaker,
) -> None:
    """One rule at a time, which is what the item asks for. An RF episode
    sits at a receiver and a track gap at an aircraft; grouping the two by
    distance would fuse them by accident, and fusing them deliberately is
    `anom-005`'s job through the proximity query instead."""
    # spec: db-009, anom-005
    store(
        factory,
        finding(subject="gap", location=A),
        finding(subject="rf", location=B, rule_id="RF-NOISE"),
    )

    assert subjects(clusters(factory)) == [["gap"]]


@pytest.mark.database
@requires_database
def test_a_finding_overlapping_the_window_is_included(factory: sessionmaker) -> None:
    """Overlap, not containment, for the reason `db-004` gives: a gap that
    began before the window opened is still happening during it."""
    # spec: db-009, db-004
    store(
        factory,
        finding(
            subject="straddles-start",
            location=A,
            started_at=START + timedelta(seconds=50),
            ended_at=START + timedelta(seconds=150),
        ),
        finding(subject="inside", location=B),
    )

    assert subjects(clusters(factory)) == [["straddles-start", "inside"]]


@pytest.mark.database
@requires_database
def test_findings_outside_the_window_are_excluded(factory: sessionmaker) -> None:
    # spec: db-009
    store(
        factory,
        finding(
            subject="before",
            location=A,
            started_at=START,
            ended_at=START + timedelta(seconds=50),
        ),
        finding(subject="inside", location=B),
    )

    assert subjects(clusters(factory)) == [["inside"]]


# ------------------------------------------------------------ failure cases


@pytest.mark.database
@requires_database
def test_nothing_to_cluster_returns_an_empty_list(factory: sessionmaker) -> None:
    """A list, not a null and not an error. A quiet run with no findings of
    a rule is the ordinary case `anom-008` requires."""
    # spec: db-009, anom-008
    assert clusters(factory) == []


@pytest.mark.database
@requires_database
def test_a_radius_of_zero_or_less_is_refused(factory: sessionmaker) -> None:
    """Refused rather than answered, for `db-004`'s reason: an empty result
    would be indistinguishable from nothing clustering, and unlike an empty
    result it is always a caller error."""
    # spec: db-009, db-004
    store(factory, finding(subject="a", location=A))

    for bad in (0.0, -5.0):
        with pytest.raises(ValueError, match="positive"):
            clusters(factory, radius_km=bad)


@pytest.mark.database
@requires_database
def test_the_scoping_filter_can_use_the_findings_index(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """Clustering aggregates over whatever the filter admits, so the filter
    is where the cost is. `db-008` created a btree index on run and rule for
    exactly this. Sequential scans are disabled for the plan so the question
    is whether the index can be used at all, not whether the planner prefers
    it on a table holding two rows."""
    # spec: db-009, db-008
    store(factory, finding(subject="a", location=A), finding(subject="b", location=B))

    with migrated_database.connect() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in connection.execute(
                text(
                    "EXPLAIN SELECT id FROM detection_findings "
                    "WHERE scenario_run_id = 1 AND rule_id = 'TRACK-GAP'"
                )
            )
        )

    assert "Index Scan" in plan or "Bitmap Index Scan" in plan, plan
