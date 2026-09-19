"""Evidence traceability. Spec: evb-002.

Every statement in a bundle must resolve to a stored row before the bundle
is allowed to exist. That is what gives `ai-008` a closed set to check a
model's citations against -- "does this claim cite something real" has no
computable answer against 20.7M observations and is a set-membership test
against a resolved bundle.

Three things make this harder than a lookup, and most of this suite is
those three:

**A ref is a coordinate, not an identifier.** `{sensor_id, channel_index,
timestamp}` or `{aircraft_id, at}`, so resolving one is a *query*, and a
query is a resolution only if it returns exactly one row. Zero is a
citation of nothing. More than one is a citation of whichever row the heap
returned first, which is the unordered-result failure this project has
recorded three times. Measured unique across 20.7M rows in
`measurements/corpus/evidence_ref_uniqueness.py` -- **within one run**, which
is why every query here is scoped and why an unscoped resolver is tested
for by name.

**Not every statement cites a row.** 72 of 332 items in real bundles carry
no refs at all: a verdict, a nominal neighbour, a rate ratio. Those are
judgements, and there is no row for a judgement. So an item *declares*
which it is, and both mismatches are refused -- otherwise "has no refs"
becomes a state an item can drift into, and the check passes by default on
anything that forgot them.

**A finding's window is not a time anything was observed.** The first pass
of this measurement found 91 of 1,021 citations resolving to zero rows,
every one the start of a `frozen_position` finding, whose window start is
reconstructed from the reported staleness rather than read. The window is
the rule's conclusion; the refs are its evidence. See `qa.md` 83.

Note what nearly hid that last one, because it shapes the first group
below: a test built on a coverage-gap finding passes, since both of its
ends are real rows. The fixture would have proved traceability working on
the one shape that cannot break it.
"""

from __future__ import annotations

from dataclasses import MISSING, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.dal.models import (
    CanonicalObservation,
    DataMode,
    Location,
    ObservationType,
    Provenance,
    SourceType,
    TrackPayload,
    ValidationStatus,
)
from app.db.bundles import (
    RF_REF_KEYS,
    TRACK_REF_KEYS,
    ResolutionError,
    bundles_for_run,
    resolve_bundles,
    save_bundles,
)
from app.db.migrations import alembic_config
from app.detection.bundle import (
    EvidenceBundle,
    EvidenceItem,
    Grounding,
    SupersededClaim,
    Uncertainty,
    UncertaintyKind,
)
from app.detection.findings import from_track_gap
from app.detection.track_gap import (
    BoundingBox,
    GapPolicy,
    GapShape,
    detect_track_gaps,
)
from tests.conftest import requires_database

BACKEND_ROOT = Path(__file__).resolve().parents[1]

RUN_ID = 1
OTHER_RUN_ID = 2

START = datetime(2022, 6, 27, 12, 0, tzinfo=UTC)
END = START + timedelta(seconds=300)
#: Cologne, from row 0 of the extract. Distinct in both coordinates and in
#: sign-free magnitude, so a lat/lon transposition cannot pass.
HERE = Location(lat=51.0905, lon=7.5473)

SENSOR = "RF-03"
CHANNEL = 4
#: A pseudonym in `dal-004`'s shape. Never a real identifier, per NFR-405.
AIRCRAFT = "AC-000000000001"

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(
    threshold=timedelta(seconds=100),
    contact_fresh_within=timedelta(seconds=30),
    box=BOX,
)


# ------------------------------------------------------------------- helpers


def track(
    *,
    aircraft_id: str = AIRCRAFT,
    timestamp: datetime = START,
    position_staleness_s: float = 1.0,
    contact_staleness_s: float = 0.0,
    on_ground: bool = False,
    location: Location = HERE,
) -> CanonicalObservation:
    return CanonicalObservation(
        source_id="opensky-replay",
        source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK,
        timestamp=timestamp,
        location=location,
        data_mode=DataMode.REPLAYED,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(
            source_id="opensky-replay",
            source_type=SourceType.OPENSKY,
            data_mode=DataMode.REPLAYED,
            scenario_run_id=RUN_ID,
        ),
        payload=TrackPayload(
            aircraft_id=aircraft_id,
            flight_id="FL-000000000001",
            altitude_m=10000.0,
            velocity_ms=200.0,
            heading_deg=90.0,
            vertical_rate_ms=0.0,
            on_ground=on_ground,
            position_staleness_s=position_staleness_s,
            contact_staleness_s=contact_staleness_s,
        ),
    )


def rf_ref(*, sensor: str = SENSOR, channel: int = CHANNEL,
           at: datetime = START) -> dict[str, Any]:
    return {"sensor_id": sensor, "channel_index": channel,
            "timestamp": at.isoformat()}


def track_ref(*, aircraft_id: str = AIRCRAFT,
              at: datetime = START) -> dict[str, Any]:
    return {"aircraft_id": aircraft_id, "at": at.isoformat()}


def observed(*refs: dict[str, Any], source: str = SENSOR) -> EvidenceItem:
    return EvidenceItem(
        source=source,
        finding="power deviated by 8.40 dB at its peak",
        rule_id="RF-NOISE",
        finding_type="rf_power_excess",
        grounding=Grounding.OBSERVED,
        data_mode=DataMode.SYNTHETIC,
        started_at=START,
        ended_at=END,
        refs=refs,
    )


def derived(*, source: str = SENSOR) -> EvidenceItem:
    return EvidenceItem(
        source=source,
        finding="its measured neighbours stayed nominal",
        rule_id="SENSOR-FAULT",
        finding_type="possible_sensor_fault",
        grounding=Grounding.DERIVED,
        data_mode=DataMode.SYNTHETIC,
        started_at=START,
        ended_at=END,
    )


def bundle(*evidence: EvidenceItem, run_id: int = RUN_ID,
           superseded: tuple[SupersededClaim, ...] = ()) -> EvidenceBundle:
    return EvidenceBundle(
        scenario_run_id=run_id,
        anomaly_type="possible_sensor_fault",
        rule_id="SENSOR-FAULT",
        subject=SENSOR,
        time_window=(START, END),
        affected_area=HERE,
        affected_channels=(CHANNEL,),
        evidence=evidence or (observed(rf_ref()),),
        known_uncertainties=(
            Uncertainty(
                kind=UncertaintyKind.NOT_APPLICABLE,
                subject="track",
                statement="the aircraft side was not consulted.",
            ),
        ),
        superseded=superseded,
    )


class _ExplodingFactory:
    """A session factory that fails if it is used at all.

    Refusals that can be decided from the bundle must be decided *before* a
    query, and this is how that is asserted rather than assumed.
    """

    def begin(self) -> Any:  # pragma: no cover -- the point is that it is not called
        raise AssertionError("resolution reached the database when it should not have")


# ---------------------------------------- the citation, not the conclusion


def test_a_frozen_position_finding_separates_what_it_read_from_what_it_concluded():
    """The window start is `first.timestamp - position_staleness`, a
    reconstruction of when the position went stale -- and that instant is by
    definition the one moment in the window at which nothing was recorded,
    because the position had stopped updating. 91 of 1,021 real citations
    pointed there."""
    # spec: anom-010, evb-002
    reports = [
        track(timestamp=START, position_staleness_s=1.0),
        track(timestamp=START + timedelta(seconds=10), position_staleness_s=400.0),
        track(timestamp=START + timedelta(seconds=20), position_staleness_s=410.0),
    ]
    found = [f for f in detect_track_gaps(reports, POLICY)
             if f.shape is GapShape.FROZEN_POSITION]
    assert len(found) == 1
    finding = found[0]

    assert finding.started_at < finding.observed_at[0], (
        "the window must start before anything was observed, or the "
        "reconstruction has been lost"
    )
    assert finding.observed_at == (START + timedelta(seconds=10),
                                   START + timedelta(seconds=20))


def test_a_not_heard_finding_read_exactly_the_reports_its_window_names():
    """The other mechanism's ends *are* observations -- the reports either
    side of the silence -- so here the two kinds of time coincide. This is
    the shape that would have made a traceability test pass while the other
    was broken."""
    # spec: anom-010, evb-002
    late = START + timedelta(seconds=300)
    found = detect_track_gaps([track(timestamp=START), track(timestamp=late)], POLICY)
    assert len(found) == 1
    assert found[0].shape is GapShape.NOT_HEARD
    assert found[0].observed_at == (found[0].started_at, found[0].ended_at)


def test_a_frozen_findings_refs_cite_reports_and_not_the_reconstructed_start():
    """`evidence_refs` is a citation field and a citation must name a row."""
    # spec: db-008, anom-010, evb-002
    reports = [
        track(timestamp=START, position_staleness_s=1.0),
        track(timestamp=START + timedelta(seconds=10), position_staleness_s=400.0),
        track(timestamp=START + timedelta(seconds=20), position_staleness_s=410.0),
    ]
    finding = [f for f in detect_track_gaps(reports, POLICY)
               if f.shape is GapShape.FROZEN_POSITION][0]
    stored = from_track_gap(finding, scenario_run_id=RUN_ID)

    cited = [ref["at"] for ref in stored.evidence_refs]
    assert finding.started_at.isoformat() not in cited
    assert cited == [finding.observed_at[0].isoformat(),
                     finding.observed_at[1].isoformat()]


# --------------------------------------- an item declares what it is claiming


def test_an_item_claiming_an_observation_must_cite_one():
    """Otherwise "carries no refs" is a state an item can drift into, and a
    check that skips such items passes by default on anything that forgot
    them -- the same defect as a sort key that does not exist."""
    # spec: evb-001, evb-002
    with pytest.raises(ValueError, match="cites nothing"):
        EvidenceItem(
            source=SENSOR, finding="power deviated", rule_id="RF-NOISE",
            finding_type="rf_power_excess", grounding=Grounding.OBSERVED,
            data_mode=DataMode.SYNTHETIC, started_at=START, ended_at=END,
        )


def test_an_item_making_a_judgement_must_not_cite_observations():
    """The declaration must not be able to lie in either direction."""
    # spec: evb-001, evb-002
    with pytest.raises(ValueError, match="judgement"):
        EvidenceItem(
            source=SENSOR, finding="its neighbours stayed nominal",
            rule_id="SENSOR-FAULT", finding_type="possible_sensor_fault",
            grounding=Grounding.DERIVED, data_mode=DataMode.SYNTHETIC,
            started_at=START, ended_at=END, refs=(rf_ref(),),
        )


def test_a_derived_item_is_never_looked_up():
    """A judgement has no row, so it must not be queried for one -- and must
    not therefore fail resolution."""
    # spec: evb-002
    resolved = resolve_bundles(_ExplodingFactory(), [bundle(derived())])
    assert resolved[0].evidence[0].observation_ids == ()


# ------------------------------------------ the coordinate shapes are closed


def test_a_ref_in_neither_known_shape_is_refused_by_name():
    """`from_track_cluster` emits `{aircraft_id}` with no time at all, which
    as a predicate matches every report that aircraft made. A resolver
    assembled from whatever keys happen to be present would build an empty
    predicate for an empty ref and match the whole run."""
    # spec: evb-002, db-008
    with pytest.raises(ResolutionError, match="aircraft_id"):
        resolve_bundles(_ExplodingFactory(),
                        [bundle(observed({"aircraft_id": AIRCRAFT}))])


def test_an_empty_ref_is_refused_rather_than_matching_everything():
    # spec: evb-002
    with pytest.raises(ResolutionError):
        resolve_bundles(_ExplodingFactory(), [bundle(observed({}))])


def test_a_ref_carrying_an_extra_key_is_refused():
    """Exact shape rather than a superset: an unexpected key means the ref
    shape has changed, and the resolver is the thing that must be told."""
    # spec: evb-002
    extra = {**rf_ref(), "band": "L"}
    with pytest.raises(ResolutionError, match="band"):
        resolve_bundles(_ExplodingFactory(), [bundle(observed(extra))])


def test_the_resolver_knows_exactly_the_shapes_the_rules_emit():
    """RF cites `timestamp` and track cites `at`. A resolver reading
    `timestamp` alone misses every track ref while appearing to work, so the
    shapes are asserted against what the rules actually produce rather than
    against this file's own helpers -- which would only prove the helpers
    agree with themselves."""
    # spec: evb-002, db-008, anom-001, anom-010
    late = START + timedelta(seconds=300)
    gap = detect_track_gaps([track(timestamp=START), track(timestamp=late)], POLICY)[0]
    emitted = from_track_gap(gap, scenario_run_id=RUN_ID).evidence_refs[0]

    assert set(emitted) == TRACK_REF_KEYS
    assert RF_REF_KEYS != TRACK_REF_KEYS
    assert "timestamp" in RF_REF_KEYS and "timestamp" not in TRACK_REF_KEYS


def test_an_evidence_item_cannot_acquire_a_grounding_by_omission():
    """No default. A default is the drift this field exists to prevent: a
    new item type that forgets to declare would inherit whichever value was
    convenient, and if that value were DERIVED it would escape the check
    entirely."""
    # spec: evb-001, evb-002
    declared = {f.name: f for f in fields(EvidenceItem)}
    assert declared["grounding"].default is MISSING
    assert declared["grounding"].default_factory is MISSING


# -------------------------------------------------------------------- fixtures


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    """An empty schema at head holding two runs, so scoping is testable."""
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", empty_database.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")

    with empty_database.connect() as connection:
        for run_id in (RUN_ID, OTHER_RUN_ID):
            connection.execute(
                text(
                    "INSERT INTO scenario_runs "
                    "(id, scenario_type, parameters, seed, started_at) "
                    "VALUES (:id, 'rf-sensor-fault', '{}'::jsonb, 42, now())"
                ),
                {"id": run_id},
            )
        connection.commit()
    return empty_database


@pytest.fixture
def factory(migrated_database: Engine) -> sessionmaker:
    return sessionmaker(bind=migrated_database, autoflush=False)


def insert_rf(engine: Engine, *, run_id: int = RUN_ID, sensor: str = SENSOR,
              channel: int = CHANNEL, at: datetime = START) -> int:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "INSERT INTO observations (source_id, source_type, data_mode, "
                " scenario_run_id, observation_type, timestamp, "
                " validation_status, provenance, payload, location) "
                "VALUES ('synthetic-rf', 'synthetic_rf', 'synthetic', :run, "
                " 'rf', :at, 'valid', '{}'::jsonb, CAST(:payload AS jsonb), "
                " ST_GeomFromEWKT('SRID=4326;POINT(7.5473 51.0905)')) "
                "RETURNING id"
            ),
            {
                "run": run_id,
                "at": at,
                "payload": (
                    f'{{"sensor_id": "{sensor}", "channel_index": {channel}, '
                    f'"centre_frequency_mhz": 1090.0, "band": "L", '
                    f'"power_dbm": -70.0}}'
                ),
            },
        ).scalar_one()
        connection.commit()
    return int(row)


def insert_track(engine: Engine, *, run_id: int = RUN_ID,
                 aircraft_id: str = AIRCRAFT, at: datetime = START) -> int:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "INSERT INTO observations (source_id, source_type, data_mode, "
                " scenario_run_id, observation_type, timestamp, "
                " validation_status, provenance, payload, location) "
                "VALUES ('opensky-replay', 'opensky', 'replayed', :run, "
                " 'track', :at, 'valid', '{}'::jsonb, CAST(:payload AS jsonb), "
                " ST_GeomFromEWKT('SRID=4326;POINT(7.5473 51.0905)')) "
                "RETURNING id"
            ),
            {
                "run": run_id,
                "at": at,
                "payload": (
                    f'{{"aircraft_id": "{aircraft_id}", "on_ground": false, '
                    f'"position_staleness_s": 1.0, "contact_staleness_s": 0.0}}'
                ),
            },
        ).scalar_one()
        connection.commit()
    return int(row)


def _count(engine: Engine, table: str = "evidence_bundles") -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        )


# ------------------------------------------------ resolution, against real rows


@pytest.mark.database
@requires_database
def test_a_cited_observation_resolves_to_its_row(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    # spec: evb-002
    row_id = insert_rf(migrated_database)
    resolved = resolve_bundles(factory, [bundle(observed(rf_ref()))])
    assert resolved[0].evidence[0].observation_ids == (row_id,)


@pytest.mark.database
@requires_database
def test_ids_come_back_in_the_order_the_refs_were_cited(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """A set would lose which id answers which citation, and `ai-008` checks
    a citation rather than a bundle."""
    # spec: evb-002, ai-008
    later = START + timedelta(seconds=10)
    second = insert_rf(migrated_database, at=later)
    first = insert_rf(migrated_database, at=START)
    resolved = resolve_bundles(
        factory, [bundle(observed(rf_ref(at=START), rf_ref(at=later)))])
    assert resolved[0].evidence[0].observation_ids == (first, second)


@pytest.mark.database
@requires_database
def test_a_citation_matching_nothing_is_refused(factory: sessionmaker) -> None:
    """The measured failure: 91 of 1,021 real citations, every one a
    reconstructed frozen-position start."""
    # spec: evb-002
    with pytest.raises(ResolutionError, match="no stored observation"):
        resolve_bundles(factory, [bundle(observed(rf_ref()))])


@pytest.mark.database
@requires_database
def test_a_citation_matching_two_rows_is_refused(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Worse than matching nothing: the bundle would cite whichever row the
    heap returned first, and nothing anywhere would say so. Measured unique
    across 20.7M rows, which is a property of the corpus and not a
    constraint the schema enforces -- so it is checked rather than assumed."""
    # spec: evb-002
    insert_rf(migrated_database)
    insert_rf(migrated_database)
    with pytest.raises(ResolutionError, match="2 stored observations"):
        resolve_bundles(factory, [bundle(observed(rf_ref()))])


@pytest.mark.database
@requires_database
def test_resolution_is_scoped_to_the_run(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Uniqueness was measured *within* one run. The same coordinate exists
    in every run of the corpus, so an unscoped resolver matches 300 rows and
    cites whichever came back first."""
    # spec: evb-002
    mine = insert_rf(migrated_database, run_id=RUN_ID)
    insert_rf(migrated_database, run_id=OTHER_RUN_ID)
    resolved = resolve_bundles(factory, [bundle(observed(rf_ref()))])
    assert resolved[0].evidence[0].observation_ids == (mine,)


@pytest.mark.database
@requires_database
def test_a_coordinate_that_exists_only_in_another_run_is_refused(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The same assertion from the other side: scoping must exclude, not
    merely prefer."""
    # spec: evb-002
    insert_rf(migrated_database, run_id=OTHER_RUN_ID)
    with pytest.raises(ResolutionError, match="no stored observation"):
        resolve_bundles(factory, [bundle(observed(rf_ref()))])


@pytest.mark.database
@requires_database
def test_a_track_citation_resolves_on_its_own_coordinate(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The second shape, which spells its time `at` rather than `timestamp`."""
    # spec: evb-002
    row_id = insert_track(migrated_database)
    item = EvidenceItem(
        source=AIRCRAFT, finding="reporting broke during the window",
        rule_id="TRACK-GAP", finding_type="track_discontinuity",
        grounding=Grounding.OBSERVED, data_mode=DataMode.REPLAYED,
        started_at=START, ended_at=END, refs=(track_ref(),))
    resolved = resolve_bundles(factory, [bundle(item)])
    assert resolved[0].evidence[0].observation_ids == (row_id,)


@pytest.mark.database
@requires_database
def test_a_bundle_spanning_both_shapes_resolves_both(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """A fusion bundle cites both by definition -- that is what makes it a
    fusion -- and the two are resolved in one query each rather than one
    query per citation. 18.6x at the median, measured."""
    # spec: evb-002, evb-001
    rf_id = insert_rf(migrated_database)
    track_id = insert_track(migrated_database)
    track_item = EvidenceItem(
        source=AIRCRAFT, finding="reporting broke during the window",
        rule_id="TRACK-GAP", finding_type="track_discontinuity",
        grounding=Grounding.OBSERVED, data_mode=DataMode.REPLAYED,
        started_at=START, ended_at=END, refs=(track_ref(),))
    resolved = resolve_bundles(
        factory, [bundle(observed(rf_ref()), track_item, derived())])
    ids = [item.observation_ids for item in resolved[0].evidence]
    assert ids == [(rf_id,), (track_id,), ()]


# ------------------------------------------------------------------ persistence


@pytest.mark.database
@requires_database
def test_the_bundles_table_carries_what_a_bundle_actually_is(
    migrated_database: Engine,
) -> None:
    """`0001` created it with a type, two blobs and a timestamp, before any
    of this existed."""
    # spec: evb-002, db-001
    with migrated_database.connect() as connection:
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'evidence_bundles'"
                )
            )
        }
    assert {
        "scenario_run_id", "rule_id", "subject", "started_at", "ended_at",
        "affected_area", "affected_channels", "evidence",
        "known_uncertainties", "superseded",
    } <= columns


@pytest.mark.database
@requires_database
def test_the_affected_area_is_a_point_at_srid_4326(
    migrated_database: Engine,
) -> None:
    """A point and not a polygon, following `anom-013`'s zone and
    `FindingCluster`: a radio anomaly is located at the receiver, and
    inventing an extent would claim ground nothing was observed across."""
    # spec: evb-002, db-001
    with migrated_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT type, srid FROM geometry_columns "
                "WHERE f_table_name = 'evidence_bundles' "
                "AND f_geometry_column = 'affected_area'"
            )
        ).one()
    assert (row.type, row.srid) == ("POINT", 4326)


@pytest.mark.database
@requires_database
def test_a_saved_bundle_comes_back_with_its_resolved_ids(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The ids are what `ai-008` verifies a citation against, so they must
    survive the round trip attached to the item that cited them."""
    # spec: evb-002, ai-008
    row_id = insert_rf(migrated_database)
    save_bundles(factory, scenario_run_id=RUN_ID,
                 bundles=[bundle(observed(rf_ref()), derived())])

    read = bundles_for_run(factory, RUN_ID)
    assert len(read) == 1
    assert read[0].subject == SENSOR
    assert read[0].time_window == (START, END)
    assert read[0].affected_channels == (CHANNEL,)
    assert read[0].evidence[0].observation_ids == (row_id,)
    assert read[0].evidence[1].grounding is Grounding.DERIVED
    assert read[0].known_uncertainties[0].kind is UncertaintyKind.NOT_APPLICABLE


@pytest.mark.database
@requires_database
def test_a_superseded_claim_survives_the_round_trip_outside_the_evidence(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """A rejected competing explanation is a real uncertainty, and reading
    it as supporting evidence inverts the truth exactly."""
    # spec: evb-002, evb-001, anom-013
    insert_rf(migrated_database)
    loser = SupersededClaim(
        rule_id="FUSION-SPATIAL", anomaly_type="possible_interference_zone",
        claimed_by="SENSOR-FAULT", reason="an earlier rule claimed this zone")
    save_bundles(factory, scenario_run_id=RUN_ID,
                 bundles=[bundle(observed(rf_ref()), superseded=(loser,))])

    read = bundles_for_run(factory, RUN_ID)
    assert read[0].superseded == (loser,)
    assert all(item.rule_id != "FUSION-SPATIAL" for item in read[0].evidence)


@pytest.mark.database
@requires_database
def test_a_failed_resolution_persists_nothing_at_all(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The item's own constraint, read at the only unit where it is
    meaningful: the good bundle is resolved and would have been written, and
    is not, because the run is the unit."""
    # spec: evb-002
    insert_rf(migrated_database)
    good = bundle(observed(rf_ref()))
    bad = bundle(observed(rf_ref(at=START + timedelta(seconds=999))))

    with pytest.raises(ResolutionError):
        save_bundles(factory, scenario_run_id=RUN_ID, bundles=[good, bad])

    assert _count(migrated_database) == 0


@pytest.mark.database
@requires_database
def test_a_second_save_replaces_rather_than_appends(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Following `db-008`: a bundle is derived from findings which are
    derived from the seed, so appending would leave a superseded bundle
    beside a current one with nothing on either to say which is which."""
    # spec: evb-002, db-008
    insert_rf(migrated_database)
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[bundle(observed(rf_ref()))])
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[bundle(observed(rf_ref()))])
    assert _count(migrated_database) == 1


@pytest.mark.database
@requires_database
def test_saving_nothing_clears_what_was_there(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The same argument at zero. A run re-detected as quiet must not leave
    last time's bundles standing, and a quiet run produces no bundles."""
    # spec: evb-002, anom-008
    insert_rf(migrated_database)
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[bundle(observed(rf_ref()))])
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[])
    assert _count(migrated_database) == 0


@pytest.mark.database
@requires_database
def test_one_runs_bundles_are_not_cleared_by_another_runs_save(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Replace is scoped to the run, or generating a batch would leave only
    the last run's bundles standing."""
    # spec: evb-002
    insert_rf(migrated_database, run_id=RUN_ID)
    insert_rf(migrated_database, run_id=OTHER_RUN_ID)
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[bundle(observed(rf_ref()))])
    save_bundles(factory, scenario_run_id=OTHER_RUN_ID,
                 bundles=[bundle(observed(rf_ref()), run_id=OTHER_RUN_ID)])
    assert len(bundles_for_run(factory, RUN_ID)) == 1
    assert len(bundles_for_run(factory, OTHER_RUN_ID)) == 1


@pytest.mark.database
@requires_database
def test_a_bundle_from_another_run_is_refused(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Writing it would file one run's event under another's id, and the
    replace above would then delete it on the next generation."""
    # spec: evb-002
    insert_rf(migrated_database)
    with pytest.raises(ResolutionError, match="run"):
        save_bundles(factory, scenario_run_id=RUN_ID,
                     bundles=[bundle(observed(rf_ref()), run_id=OTHER_RUN_ID)])


@pytest.mark.database
@requires_database
def test_an_empty_read_is_a_list_and_not_a_null(factory: sessionmaker) -> None:
    """A run with no bundles is the ordinary outcome -- `anom-008` requires
    it of every quiet run -- not an error and not a null to remember to test."""
    # spec: evb-002, anom-008
    assert bundles_for_run(factory, RUN_ID) == []


@pytest.mark.database
@requires_database
def test_the_revision_is_reversible(migrated_database: Engine) -> None:
    """An added column is exactly the kind of change that must be droppable,
    following `db-010`."""
    # spec: evb-002, db-010
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url",
        migrated_database.url.render_as_string(hide_password=False),
    )
    def columns() -> set[str]:
        with migrated_database.connect() as connection:
            return {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'evidence_bundles'"
                    )
                )
            }

    # Asserted at head first. Without this the downgrade half passes
    # vacuously against any revision that never added the column.
    assert "scenario_run_id" in columns()
    command.downgrade(config, "-1")
    assert "scenario_run_id" not in columns()
    assert "anomaly_type" in columns(), "the downgrade took the original table with it"
    command.upgrade(config, "head")
    assert "scenario_run_id" in columns()
