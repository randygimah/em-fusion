"""Spatial clustering of track discontinuities. Spec: anom-004.

A thin rule over `db-009`, and thin on purpose: the query does the
grouping, and what this adds is the rule identity, a radius, and a refusal.
Most of the tests below are about the refusal.

**Its output is an intermediate finding and cluster size is never on its
own reportable**, which is not a design preference but a measurement. Over
eight seed-matched triples the largest cluster a staged run produces is
identical to the largest cluster in its own control in all eight, at every
radius from 5 to 20 km. Clustering track gaps alone cannot tell a staged
run from a quiet one, so a rule reporting on cluster size would be
reporting background -- and `anom-011` carries the reason, which is that
`TRACK-GAP` recall is 21 per cent and the signal is the same size as the
noise it would have to be separated from.

That is why `TrackGapCluster` carries no severity, asserted here
structurally rather than trusted: the same proof `anom-010` uses, for the
same reason, one layer up.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.dal.models import Location
from app.db.findings import findings_for_run, save_findings
from app.db.migrations import alembic_config
from app.detection.clustering import (
    DEFAULT_RADIUS_KM,
    FINDING_TYPE,
    RULE_ID,
    ClusterPolicy,
    TrackGapCluster,
    cluster_track_gaps,
)
from app.detection.findings import DetectionFinding, from_track_cluster
from tests.conftest import requires_database

RUN_ID = 1
OTHER_RUN_ID = 2
SOURCE_RULE = "TRACK-GAP"

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
WINDOW = (START, START + timedelta(seconds=600))

#: Three points on one line of latitude, 4.121 km apart in sequence, and a
#: fourth 68.677 km from the first. Measured against PostGIS, not computed.
A = Location(lat=52.0, lon=5.00)
B = Location(lat=52.0, lon=5.06)
C = Location(lat=52.0, lon=5.12)
LONE = Location(lat=52.0, lon=6.00)


def gap(
    *,
    aircraft: str,
    location: Location,
    started_at: datetime = START + timedelta(seconds=150),
    ended_at: datetime = START + timedelta(seconds=200),
    scenario_run_id: int = RUN_ID,
    rule_id: str = SOURCE_RULE,
) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=rule_id,
        finding_type="track_continuity_gap",
        subject=aircraft,
        started_at=started_at,
        ended_at=ended_at,
        location=location,
        evidence_refs=({"aircraft_id": aircraft},),
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
    grouped: dict[tuple[int, str], list[DetectionFinding]] = {}
    for f in findings:
        grouped.setdefault((f.scenario_run_id, f.rule_id), []).append(f)
    for (run_id, rule_id), group in grouped.items():
        save_findings(factory, scenario_run_id=run_id, rule_id=rule_id, findings=group)


def clusters(factory: sessionmaker, **kwargs: object) -> tuple[TrackGapCluster, ...]:
    call: dict[str, object] = {
        "scenario_run_id": RUN_ID,
        "window": WINDOW,
        "policy": ClusterPolicy(radius_km=5.0),
    }
    call.update(kwargs)
    return cluster_track_gaps(factory, **call)  # type: ignore[arg-type]


def members(found: tuple[TrackGapCluster, ...]) -> list[list[str]]:
    return [list(c.members) for c in found]


# ------------------------------------------------- not reportable, by shape


def test_a_cluster_carries_no_severity() -> None:
    """The structural proof, not a promise in a docstring.

    `anom-001` gives its episodes a severity because they are shown to an
    analyst. A cluster is not: measured, the largest cluster on a staged
    run equals the largest on its own matched control in eight triples of
    eight. A severity field here would be a number with nothing behind it,
    and the way to keep it out is to have nowhere to put it.
    """
    # spec: anom-004, anom-008, anom-011
    names = {f.name for f in dataclasses.fields(TrackGapCluster)}

    assert "severity" not in names
    assert not names & {"confidence", "score", "priority"}


def test_the_rule_declares_an_intermediate_finding_type() -> None:
    # spec: anom-004
    assert RULE_ID == "TRACK-CLUSTER"
    assert FINDING_TYPE == "track_gap_cluster"
    assert not FINDING_TYPE.startswith("possible_")


# ----------------------------------------------------------------- grouping


@pytest.mark.database
@requires_database
def test_discontinuities_within_the_radius_form_one_cluster(
    factory: sessionmaker,
) -> None:
    # spec: anom-004, FR-305
    store(factory, gap(aircraft="a", location=A), gap(aircraft="b", location=B))

    assert members(clusters(factory)) == [["a", "b"]]


@pytest.mark.database
@requires_database
def test_discontinuities_beyond_the_radius_are_not_one_cluster(
    factory: sessionmaker,
) -> None:
    """The item's own named failure case, inherited unchanged."""
    # spec: anom-004
    store(factory, gap(aircraft="a", location=A), gap(aircraft="lone", location=LONE))

    assert members(clusters(factory)) == [["a"], ["lone"]]


@pytest.mark.database
@requires_database
def test_an_isolated_discontinuity_is_a_cluster_of_one(factory: sessionmaker) -> None:
    """This item originally said an isolated discontinuity forms no cluster,
    which contradicts `db-009` and would delete the signal `anom-006` reads:
    a source that goes quiet alone is an infrastructure problem rather than
    an incident. The constraint was replaced, and what a cluster of one
    means is the consuming rule's decision, not this one's."""
    # spec: anom-004, anom-006, db-009
    store(factory, gap(aircraft="lone", location=LONE))

    found = clusters(factory)

    assert members(found) == [["lone"]]
    assert found[0].size == 1


@pytest.mark.database
@requires_database
def test_the_radius_is_a_parameter_and_is_not_fitted(factory: sessionmaker) -> None:
    """Three radii, three answers. The default is the scale of a staged
    incident rather than a value chosen because it separated anything: the
    measurement covers 5 to 60 km and separates staged runs from their
    controls at none of them."""
    # spec: anom-004, anom-011
    store(
        factory,
        gap(aircraft="a", location=A),
        gap(aircraft="b", location=B),
        gap(aircraft="lone", location=LONE),
    )

    assert members(clusters(factory, policy=ClusterPolicy(radius_km=3.0))) == [
        ["a"],
        ["b"],
        ["lone"],
    ]
    assert members(clusters(factory, policy=ClusterPolicy(radius_km=5.0))) == [
        ["a", "b"],
        ["lone"],
    ]
    assert members(clusters(factory, policy=ClusterPolicy(radius_km=70.0))) == [
        ["a", "b", "lone"]
    ]


def test_the_default_radius_is_the_staged_incident_scale() -> None:
    # spec: anom-004
    assert DEFAULT_RADIUS_KM == 60.0
    assert ClusterPolicy().radius_km == DEFAULT_RADIUS_KM


@pytest.mark.database
@requires_database
def test_a_chain_forms_one_cluster_wider_than_the_radius(
    factory: sessionmaker,
) -> None:
    """The transitive property `db-009` records, surfaced here because this
    is the layer that chooses the radius and therefore owns the
    consequence."""
    # spec: anom-004, db-009
    store(
        factory,
        gap(aircraft="a", location=A),
        gap(aircraft="b", location=B),
        gap(aircraft="c", location=C),
    )

    assert members(clusters(factory)) == [["a", "b", "c"]]


# -------------------------------------------------------------------- shape


@pytest.mark.database
@requires_database
def test_a_cluster_spans_its_members_in_time(factory: sessionmaker) -> None:
    """The window is the union of the members', not the first member's. A
    cluster is the disruption, and the disruption lasted as long as its
    longest part."""
    # spec: anom-004, anom-005
    store(
        factory,
        gap(
            aircraft="early",
            location=A,
            started_at=START + timedelta(seconds=100),
            ended_at=START + timedelta(seconds=180),
        ),
        gap(
            aircraft="late",
            location=B,
            started_at=START + timedelta(seconds=220),
            ended_at=START + timedelta(seconds=400),
        ),
    )

    (found,) = clusters(factory)

    assert found.started_at == START + timedelta(seconds=100)
    assert found.ended_at == START + timedelta(seconds=400)


@pytest.mark.database
@requires_database
def test_a_cluster_carries_a_centroid_and_a_covering_shape(
    factory: sessionmaker,
) -> None:
    # spec: anom-004, FR-301
    store(factory, gap(aircraft="a", location=A), gap(aircraft="b", location=B))

    (found,) = clusters(factory)

    assert found.centroid.lat == pytest.approx(52.0, abs=1e-3)
    assert found.centroid.lon == pytest.approx(5.03, abs=1e-3)
    assert found.hull_wkt.startswith("LINESTRING")


# -------------------------------------------------------------------- scope


@pytest.mark.database
@requires_database
def test_only_track_gaps_are_clustered(factory: sessionmaker) -> None:
    """An RF episode sits at a receiver and a track gap at an aircraft.
    Grouping the two by distance would fuse them by accident; fusing them
    deliberately is `anom-005`'s job."""
    # spec: anom-004, anom-005
    store(
        factory,
        gap(aircraft="a", location=A),
        gap(aircraft="rf", location=B, rule_id="RF-NOISE"),
    )

    assert members(clusters(factory)) == [["a"]]


@pytest.mark.database
@requires_database
def test_another_run_is_never_clustered_in(factory: sessionmaker) -> None:
    # spec: anom-004, eval-002
    store(
        factory,
        gap(aircraft="mine", location=A),
        gap(aircraft="theirs", location=B, scenario_run_id=OTHER_RUN_ID),
    )

    assert members(clusters(factory)) == [["mine"]]


@pytest.mark.database
@requires_database
def test_a_run_with_no_discontinuities_clusters_to_nothing(
    factory: sessionmaker,
) -> None:
    """An empty tuple, not a null and not an error. `anom-008` requires the
    quiet case to be an ordinary outcome."""
    # spec: anom-004, anom-008
    assert clusters(factory) == ()


# ------------------------------------------------------------- determinism


@pytest.mark.database
@requires_database
def test_the_same_discontinuities_give_the_same_clusters(
    factory: sessionmaker,
) -> None:
    """NFR-601 carried up from `db-009`. A run reproduces from its seed, so
    nothing here may depend on the order rows came back."""
    # spec: anom-004, NFR-601
    written = [
        gap(aircraft="a", location=A),
        gap(aircraft="b", location=B),
        gap(aircraft="lone", location=LONE),
    ]

    store(factory, *written)
    first = clusters(factory)
    store(factory, *reversed(written))
    second = clusters(factory)

    assert first == second
    assert members(first) == [["a", "b"], ["lone"]]


# ------------------------------------------------------------ failure cases


def test_a_radius_of_zero_or_less_is_refused() -> None:
    """Refused where the policy is built, so a bad radius cannot reach the
    database at all."""
    # spec: anom-004, db-009
    for bad in (0.0, -5.0):
        with pytest.raises(ValueError, match="positive"):
            ClusterPolicy(radius_km=bad)


# --------------------------------------------- the canonical-shape prediction


@pytest.mark.database
@requires_database
def test_a_cluster_stores_through_the_unchanged_finding_shape(
    factory: sessionmaker,
) -> None:
    """`db-008` claims one shape every rule becomes, so that a new detector
    needs no change to the storage layer. This is the first chance to score
    that claim on something structurally unlike the two rules it was built
    from -- a cluster has many subjects rather than one.

    If this passes with no edit to `app/db/findings.py`, the prediction
    holds at a case it was not designed around.
    """
    # spec: anom-004, db-008
    store(factory, gap(aircraft="a", location=A), gap(aircraft="b", location=B))
    (found,) = clusters(factory)

    finding = from_track_cluster(found, scenario_run_id=RUN_ID)
    save_findings(factory, scenario_run_id=RUN_ID, rule_id=RULE_ID, findings=[finding])

    (stored,) = findings_for_run(factory, RUN_ID, rule_id=RULE_ID)

    assert stored.rule_id == RULE_ID
    assert stored.finding_type == FINDING_TYPE
    assert stored.details["size"] == 2
    assert stored.details["members"] == ["a", "b"]
    assert "severity" not in stored.details
