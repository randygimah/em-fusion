"""Detection finding persistence. Spec: db-008.

`db-004` was picked up and had nothing to query: the `anomalies` table
exists, nothing writes to it or reads it, and no item covered doing so.
This is the table the spatial queries actually read, and the seam that
lets a detector's output outlive the process that produced it.

Three groups. The **schema** group asserts the things a functional test
cannot see -- that the location is a real geometry column at the right
SRID, that its GiST index exists, and that `anomalies` finally carries
the run id it has never had. An unindexed geometry column still returns
correct answers by sequential scan, so it fails as a performance claim
rather than a correctness one, which is the kind of defect that survives
every other test in this file.

The **canonical shape** group is a unit tier and needs no database. Its
argument is `dal-001`'s, one layer along: one shape every rule becomes,
so a third detector needs no change to the storage layer at all.

The **storage** group is the live tier, and its failure cases are the
item's: an orphaned finding refused by the database rather than stored, a
backwards window refused, an empty read that is a list rather than a null,
and a second write that replaces rather than doubles.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.dal.models import Location
from app.db.findings import findings_for_run, save_findings
from app.db.migrations import alembic_config
from app.detection.baseline import RfCell, RfMetric
from app.detection.findings import (
    DetectionFinding,
    from_rf_noise,
    from_track_gap,
)
from app.detection.rf_noise import ReadingRef, RfNoiseAnomaly, Severity
from app.detection.track_gap import GapShape, TrackGapFinding
from tests.conftest import requires_database

BACKEND_ROOT = Path(__file__).resolve().parents[1]

RUN_ID = 1
#: Absent from `scenario_runs`, so writing against it violates the foreign
#: key -- a real database refusal rather than a simulated one.
MISSING_RUN_ID = 9999

START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
#: Cologne, from row 0 of the extract. Distinct in both coordinates and in
#: sign-free magnitude, so a latitude/longitude transposition cannot pass.
LAT = 51.0905
LON = 7.5473
WHERE = Location(lat=LAT, lon=LON)


def finding(
    *,
    scenario_run_id: int = RUN_ID,
    rule_id: str = "TRACK-GAP",
    subject: str = "AC-000000000001",
    started_at: datetime = START,
    ended_at: datetime = START + timedelta(seconds=200),
    location: Location = WHERE,
    details: dict[str, Any] | None = None,
) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=rule_id,
        finding_type="track_continuity_gap",
        subject=subject,
        started_at=started_at,
        ended_at=ended_at,
        location=location,
        evidence_refs=({"aircraft_id": subject, "at": started_at.isoformat()},),
        details=details or {"shape": "not_heard"},
    )


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    """An empty schema at head, holding one scenario run.

    The run exists because the findings table carries a NOT NULL foreign key
    to it, and it is inserted here rather than by the storage layer: creating
    a run is the generator's job, and a module that quietly created its own
    parent row would hide the constraint these tests rely on.
    """
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", empty_database.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")

    with empty_database.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at) "
                "VALUES (:id, 'normal-baseline', '{}'::jsonb, 42, now())"
            ),
            {"id": RUN_ID},
        )
        connection.commit()
    return empty_database


@pytest.fixture
def factory(migrated_database: Engine) -> sessionmaker:
    return sessionmaker(bind=migrated_database, autoflush=False)


def _count(engine: Engine, where: str = "true") -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(f"SELECT count(*) FROM detection_findings WHERE {where}")
            ).scalar_one()
        )


# ---------------------------------------------------------------- the schema


@pytest.mark.database
@requires_database
def test_the_findings_table_exists_after_migration(migrated_database: Engine) -> None:
    # spec: db-008, db-001
    assert _count(migrated_database) == 0


@pytest.mark.database
@requires_database
def test_the_location_is_a_point_at_srid_4326(migrated_database: Engine) -> None:
    """Not two float columns. `db-004` computes distance on geography, and
    it can only do that against a real geometry at a known SRID -- without
    it a later 'within 20 km' question answers in degrees instead."""
    # spec: db-008, FR-905
    with migrated_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT type, srid, coord_dimension FROM geometry_columns "
                "WHERE f_table_name = 'detection_findings' "
                "AND f_geometry_column = 'location'"
            )
        ).one()

    assert (row.type, row.srid, row.coord_dimension) == ("POINT", 4326, 2)


@pytest.mark.database
@requires_database
def test_the_location_carries_a_gist_index(migrated_database: Engine) -> None:
    """`db-001` created one on the anomalies geometry and named `db-004` as
    the reason. The findings `db-004` and `anom-004` query live here, so the
    index belongs here too -- and an unindexed column still returns correct
    answers by sequential scan, which is why this is asserted rather than
    left to be noticed."""
    # spec: db-008, db-001, db-004
    with migrated_database.connect() as connection:
        indexdef = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'detection_findings' "
                "AND indexdef ILIKE '%location%'"
            )
        ).scalar_one()

    assert "USING gist" in indexdef


@pytest.mark.database
@requires_database
def test_anomalies_now_carries_the_run_it_belongs_to(
    migrated_database: Engine,
) -> None:
    """It never has. Every metric in `eval-002` is computed per run against
    that run's recorded ground truth, so an anomaly that cannot name its run
    cannot be scored."""
    # spec: db-008, db-001, eval-002
    with migrated_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'anomalies' AND column_name = 'scenario_run_id'"
            )
        ).one()

    assert (row.data_type, row.is_nullable) == ("integer", "NO")


# -------------------------------------------------------- the canonical shape
#
# Unit tier: no database. One shape every rule becomes, so the storage layer
# gains no branch per rule -- `dal-001`'s argument, one layer along.


def test_an_rf_episode_becomes_a_canonical_finding() -> None:
    # spec: db-008, anom-001
    anomaly = RfNoiseAnomaly(
        cell=RfCell("RF-03", 4),
        metric=RfMetric.POWER_DBM,
        severity=Severity.MEDIUM,
        started_at=START,
        ended_at=START + timedelta(seconds=60),
        location=WHERE,
        peak_deviation=11.5,
        triggering=(ReadingRef("RF-03", 4, START),),
    )

    converted = from_rf_noise(anomaly, scenario_run_id=RUN_ID)

    assert converted.rule_id == "RF-NOISE"
    assert converted.finding_type == "rf_noise_deviation"
    assert converted.subject == "RF-03:4"
    assert converted.location == WHERE
    assert converted.details["severity"] == "medium"
    assert converted.details["peak_deviation"] == 11.5


def test_a_track_gap_becomes_a_canonical_finding() -> None:
    # spec: db-008, anom-010
    gap = TrackGapFinding(
        aircraft_id="AC-000000000001",
        shape=GapShape.FROZEN_POSITION,
        started_at=START,
        ended_at=START + timedelta(seconds=200),
        location=WHERE,
        # What the rule read, which for this shape is not the window: the
        # start is reconstructed from the reported staleness (`evb-002`).
        observed_at=(START + timedelta(seconds=150),
                     START + timedelta(seconds=200)),
    )

    converted = from_track_gap(gap, scenario_run_id=RUN_ID)

    assert converted.rule_id == "TRACK-GAP"
    assert converted.finding_type == "track_continuity_gap"
    assert converted.subject == "AC-000000000001"
    assert converted.details["shape"] == "frozen_position"


def test_the_two_rules_produce_the_same_shape() -> None:
    """The point of the canonical model: a third detector adds no branch to
    the storage layer. Asserted on the field set rather than by inspection,
    so a rule-specific field added to one of them fails here."""
    # spec: db-008, dal-001
    rf = from_rf_noise(
        RfNoiseAnomaly(
            cell=RfCell("RF-01", 0),
            metric=RfMetric.POWER_DBM,
            severity=Severity.LOW,
            started_at=START,
            ended_at=START,
            location=WHERE,
            peak_deviation=7.0,
            triggering=(ReadingRef("RF-01", 0, START),),
        ),
        scenario_run_id=RUN_ID,
    )
    gap = from_track_gap(
        TrackGapFinding(
            aircraft_id="AC-1",
            shape=GapShape.NOT_HEARD,
            started_at=START,
            ended_at=START + timedelta(seconds=200),
            location=WHERE,
            observed_at=(START, START + timedelta(seconds=200)),
        ),
        scenario_run_id=RUN_ID,
    )

    assert type(rf) is type(gap) is DetectionFinding
    # Named explicitly, so a rule-specific column added at the top level --
    # a severity for the RF rule, say -- fails here rather than quietly
    # putting a branch per rule into the storage layer.
    assert [f.name for f in fields(DetectionFinding)] == [
        "scenario_run_id",
        "rule_id",
        "finding_type",
        "subject",
        "started_at",
        "ended_at",
        "location",
        "evidence_refs",
        "details",
    ]


def test_evidence_refs_are_already_json_ready() -> None:
    """Timestamps go in as strings, so what is read back equals what was
    written. A datetime inside the payload would round-trip to a string and
    make every equality assertion in the storage group false."""
    # spec: db-008, evb-002
    anomaly = RfNoiseAnomaly(
        cell=RfCell("RF-03", 4),
        metric=RfMetric.POWER_DBM,
        severity=Severity.HIGH,
        started_at=START,
        ended_at=START,
        location=WHERE,
        peak_deviation=20.0,
        triggering=(ReadingRef("RF-03", 4, START),),
    )

    (ref,) = from_rf_noise(anomaly, scenario_run_id=RUN_ID).evidence_refs

    assert ref == {
        "sensor_id": "RF-03",
        "channel_index": 4,
        "timestamp": START.isoformat(),
    }


# --------------------------------------------------------------- the storage


@pytest.mark.database
@requires_database
def test_a_finding_round_trips(factory: sessionmaker) -> None:
    # spec: db-008
    written = finding()

    save_findings(
        factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[written]
    )

    assert findings_for_run(factory, RUN_ID) == [written]


@pytest.mark.database
@requires_database
def test_the_location_is_stored_at_the_coordinates_it_was_given(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """Longitude first in the geometry, latitude second -- the opposite of
    how people say them, and a reliable way to put every finding in the
    wrong place while nothing complains."""
    # spec: db-008, db-003
    save_findings(
        factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[finding()]
    )

    with migrated_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT ST_X(location) AS lon, ST_Y(location) AS lat "
                "FROM detection_findings"
            )
        ).one()

    assert (row.lat, row.lon) == (LAT, LON)


@pytest.mark.database
@requires_database
def test_reading_a_run_with_no_findings_returns_an_empty_list(
    factory: sessionmaker,
) -> None:
    """The item's third failure case: a list, not a null and not an error."""
    # spec: db-008
    assert findings_for_run(factory, RUN_ID) == []


@pytest.mark.database
@requires_database
def test_a_finding_naming_a_run_that_does_not_exist_is_refused(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """Refused by the database, not by the caller remembering to check."""
    # spec: db-008
    with pytest.raises(IntegrityError):
        save_findings(
            factory,
            scenario_run_id=MISSING_RUN_ID,
            rule_id="TRACK-GAP",
            findings=[finding(scenario_run_id=MISSING_RUN_ID)],
        )

    assert _count(migrated_database) == 0


@pytest.mark.database
@requires_database
def test_a_window_that_ends_before_it_begins_is_refused(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """A constraint rather than a convention. `api-006` had exactly this
    defect in its request model and it produced twenty mislabelled runs."""
    # spec: db-008
    backwards = finding(started_at=START, ended_at=START - timedelta(seconds=1))

    with pytest.raises((IntegrityError, DBAPIError)):
        save_findings(
            factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[backwards]
        )

    assert _count(migrated_database) == 0


@pytest.mark.database
@requires_database
def test_writing_the_same_rule_twice_replaces_rather_than_doubles(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """The item's fourth failure case. Detection is regenerable from the
    run's seed, so findings are derived rather than historical -- and after
    a rule changes, appending would leave the old set beside the new with
    every metric counting both, silently."""
    # spec: db-008, NFR-601
    for _ in range(2):
        save_findings(
            factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[finding()]
        )

    assert _count(migrated_database) == 1


@pytest.mark.database
@requires_database
def test_replacing_one_rule_leaves_another_rules_findings_alone(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """Per run *per rule*. Re-running the track rule must not silently
    delete what the RF rule found on the same run."""
    # spec: db-008
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id="RF-NOISE",
        findings=[finding(rule_id="RF-NOISE")],
    )
    save_findings(
        factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[finding()]
    )
    save_findings(
        factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[finding()]
    )

    assert _count(migrated_database, "rule_id = 'RF-NOISE'") == 1
    assert _count(migrated_database, "rule_id = 'TRACK-GAP'") == 1


@pytest.mark.database
@requires_database
def test_findings_can_be_read_back_for_one_rule(factory: sessionmaker) -> None:
    # spec: db-008
    rf = finding(rule_id="RF-NOISE", subject="RF-01:0")
    save_findings(factory, scenario_run_id=RUN_ID, rule_id="RF-NOISE", findings=[rf])
    save_findings(
        factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[finding()]
    )

    assert findings_for_run(factory, RUN_ID, rule_id="RF-NOISE") == [rf]


@pytest.mark.database
@requires_database
def test_writing_no_findings_clears_what_was_there(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    """A rule that found nothing this time must not leave last time's
    findings standing. It is the same argument as replacing, at zero."""
    # spec: db-008
    save_findings(
        factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[finding()]
    )
    save_findings(factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[])

    assert _count(migrated_database) == 0


@pytest.mark.database
@requires_database
def test_findings_of_one_run_are_not_returned_for_another(
    factory: sessionmaker, migrated_database: Engine
) -> None:
    # spec: db-008, eval-002
    with migrated_database.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at) "
                "VALUES (2, 'gnss-degradation', '{}'::jsonb, 43, now())"
            )
        )
        connection.commit()
    save_findings(
        factory, scenario_run_id=RUN_ID, rule_id="TRACK-GAP", findings=[finding()]
    )

    assert findings_for_run(factory, 2) == []
