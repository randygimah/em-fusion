"""Local discontinuity rate excess. Spec: anom-012.

The track side's contribution to fusion, replacing cluster size because
cluster size carries no signal: over 40 matched pairs the largest cluster
on a staged run beats its own control in 1 to 3, at every radius from 5 to
60 km.

This asks a different question. **At this place, are discontinuities more
frequent during this window than at the same place outside it?** The
comparison is internal to one run and one location, so it controls for the
two things that defeated clustering -- air traffic is not uniform, and runs
differ from one another. Pooled over 40 pairs the separation is real at
every radius (p = 0.047, 0.006, 0.001) and still weak in absolute terms, a
Youden's J of 0.23 to 0.40 where zero is a coin flip.

This item computes the number. It sets **no threshold**: which point on the
trade-off curve is right depends on `anom-013`'s rule ordering and on
`anom-007`'s measured catch rate, neither of which exists yet.

The disc is selected with `db-004` rather than by measuring distance here,
because a second copy of the distance rule is the trap this repository has
already recorded once.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.dal.models import Location
from app.db.findings import save_findings
from app.db.migrations import alembic_config
from app.detection.findings import DetectionFinding
from app.detection.rate_excess import ExcessPolicy, RateExcess, measure_rate_excess
from tests.conftest import requires_database

RUN_ID = 1
OTHER_RUN_ID = 2
SOURCE_RULE = "TRACK-GAP"

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
#: A 900 s run with a 300 s window 120 s in, matching the generator.
RUN_SPAN = (START, START + timedelta(seconds=900))
WINDOW = (START + timedelta(seconds=120), START + timedelta(seconds=420))

CENTRE = Location(lat=52.0, lon=5.0)
NEAR = Location(lat=52.0, lon=5.06)
FAR = Location(lat=52.0, lon=7.0)

POLICY = ExcessPolicy(radius_km=30.0)


def finding(
    *,
    subject: str,
    at: float,
    duration: float = 50.0,
    location: Location = NEAR,
    scenario_run_id: int = RUN_ID,
    rule_id: str = SOURCE_RULE,
) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=rule_id,
        finding_type="track_continuity_gap",
        subject=subject,
        started_at=START + timedelta(seconds=at),
        ended_at=START + timedelta(seconds=at + duration),
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
            (OTHER_RUN_ID, "rf-sensor-fault"),
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


def measure(factory: sessionmaker, **kwargs: object) -> RateExcess:
    call: dict[str, object] = {
        "scenario_run_id": RUN_ID,
        "centre": CENTRE,
        "policy": POLICY,
        "window": WINDOW,
        "run_span": RUN_SPAN,
    }
    call.update(kwargs)
    return measure_rate_excess(factory, **call)  # type: ignore[arg-type]


# ------------------------------------------------ the number it is asked for


@pytest.mark.database
@requires_database
def test_findings_concentrated_in_the_window_give_an_excess(
    factory: sessionmaker,
) -> None:
    # spec: anom-012, FR-305
    store(
        factory,
        finding(subject="a", at=150),
        finding(subject="b", at=250),
        finding(subject="c", at=350),
        finding(subject="quiet", at=700),
    )

    result = measure(factory)

    assert result.during == 3
    assert result.outside == 1
    assert result.excess > 0
    assert result.ratio > 1


@pytest.mark.database
@requires_database
def test_a_place_with_nothing_happening_has_no_excess(factory: sessionmaker) -> None:
    """The item's named failure case: an excess of zero, not an error."""
    # spec: anom-012
    store(factory, finding(subject="elsewhere", at=200, location=FAR))

    result = measure(factory)

    assert result.during == result.outside == 0
    assert result.excess == pytest.approx(0.0)


@pytest.mark.database
@requires_database
def test_the_comparison_is_a_rate_and_not_a_count(factory: sessionmaker) -> None:
    """The item's sharpest failure case. The window is 300 s and the rest of
    the run is 600 s, so two findings in each is **twice** the rate inside,
    not the same. A count would report no excess where there is one."""
    # spec: anom-012
    store(
        factory,
        finding(subject="in-1", at=150),
        finding(subject="in-2", at=250),
        finding(subject="out-1", at=500),
        finding(subject="out-2", at=700),
    )

    result = measure(factory)

    assert result.during == result.outside == 2
    assert result.during_per_minute == pytest.approx(2 * 60 / 300)
    assert result.outside_per_minute == pytest.approx(2 * 60 / 600)
    assert result.ratio > 1.5


@pytest.mark.database
@requires_database
def test_a_finding_overlapping_the_window_counts_as_during(
    factory: sessionmaker,
) -> None:
    """Overlap, for `db-004`'s reason: a gap that began before the window
    opened is still happening during it."""
    # spec: anom-012, db-004
    store(factory, finding(subject="straddles", at=90, duration=60))

    assert measure(factory).during == 1


# --------------------------------------------------------- scope of the disc


@pytest.mark.database
@requires_database
def test_findings_outside_the_radius_are_not_counted(factory: sessionmaker) -> None:
    # spec: anom-012, db-004
    store(
        factory,
        finding(subject="near", at=200),
        finding(subject="far", at=200, location=FAR),
    )

    result = measure(factory)

    assert result.during == 1


@pytest.mark.database
@requires_database
def test_the_radius_is_a_parameter(factory: sessionmaker) -> None:
    """FAR is about 137 km away, so a wide enough disc admits it. The radius
    is not fixed here: which point on the trade-off curve is right depends
    on `anom-013`'s ordering, which is unsettled."""
    # spec: anom-012, anom-013
    store(
        factory,
        finding(subject="near", at=200),
        finding(subject="far", at=200, location=FAR),
    )

    assert measure(factory, policy=ExcessPolicy(radius_km=30.0)).during == 1
    assert measure(factory, policy=ExcessPolicy(radius_km=200.0)).during == 2


@pytest.mark.database
@requires_database
def test_only_track_gaps_are_counted(factory: sessionmaker) -> None:
    """An RF episode sits at a receiver. Counting it here would make the
    track side's evidence partly the radio side's, which is exactly the
    independence `anom-005` relies on."""
    # spec: anom-012, anom-005
    store(
        factory,
        finding(subject="gap", at=200),
        finding(subject="rf", at=200, rule_id="RF-NOISE"),
    )

    assert measure(factory).during == 1


@pytest.mark.database
@requires_database
def test_another_run_is_never_counted(factory: sessionmaker) -> None:
    # spec: anom-012, eval-002
    store(
        factory,
        finding(subject="mine", at=200),
        finding(subject="theirs", at=200, scenario_run_id=OTHER_RUN_ID),
    )

    assert measure(factory).during == 1


# --------------------------------------------------------- what it refuses


def test_a_window_covering_the_whole_run_is_refused() -> None:
    """No reference period, so there is nothing to compare against. An
    excess computed against an empty remainder would be an artefact of the
    window rather than a property of the place."""
    # spec: anom-012
    with pytest.raises(ValueError, match="reference"):
        measure_rate_excess(
            None,  # type: ignore[arg-type]
            scenario_run_id=RUN_ID,
            centre=CENTRE,
            policy=POLICY,
            window=RUN_SPAN,
            run_span=RUN_SPAN,
        )


def test_a_radius_of_zero_or_less_is_refused() -> None:
    # spec: anom-012, db-004
    for bad in (0.0, -5.0):
        with pytest.raises(ValueError, match="positive"):
            ExcessPolicy(radius_km=bad)


def test_the_result_carries_no_severity_and_no_threshold() -> None:
    """Structural, as `anom-004` and `anom-010` do it. This item computes a
    number; `anom-005` decides what the number means. A threshold stored
    here would be a decision made where it cannot be seen -- and the curve
    it would come from is a trade-off, not a maximum."""
    # spec: anom-012, anom-013
    names = {f.name for f in dataclasses.fields(RateExcess)}

    assert not names & {"severity", "threshold", "confidence", "score", "reportable"}


def test_the_policy_has_no_default_radius() -> None:
    """Deliberate. Every measured point is a different trade-off between a
    missed incident and a misattributed one, and a default would quietly
    make that choice for the caller."""
    # spec: anom-012, anom-013
    with pytest.raises(TypeError):
        ExcessPolicy()  # type: ignore[call-arg]
