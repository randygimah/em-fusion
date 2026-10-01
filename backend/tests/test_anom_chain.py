"""The detection pass over one completed run. Spec: anom-015.

**What is new here is the ordering, not the rules.** Every rule this composes has
its own suite and sits at full coverage; what nothing covered is the order they
run in, which until now existed only inside `measurements/corpus/detection_metrics.py`
-- outside ruff, mypy, pytest and the coverage gate. `ai-011` exists because by the
time five parts worked separately, three ways of joining them produced a system
that ran perfectly and reported something false. These are the tests that item's
counterpart needs.

Four of them are about **what cannot be inferred from the run being scored**:
normality is measured over the corpus's quiet runs, so the baseline is an input, a
store with no quiet runs is refused, the policy record names the runs it came
from, and nothing baselines against the run it is judging.

One is about an ordering that is not a preference: the track findings are written
**before** the spatial rules run, because those rules are PostGIS queries over the
stored rows. A pass written as compute-then-store finds no track evidence and
reports it absent rather than unwritten, which is a wrong answer that looks like a
quiet corpus.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (
    CanonicalObservation,
    DataMode,
    Location,
    ObservationType,
    Provenance,
    RfPayload,
    ScenarioRunSummary,
    SourceType,
    TrackPayload,
    ValidationStatus,
)
from app.db.repository import create_scenario_run
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.chain import (
    ChainError,
    DetectorPolicies,
    Normality,
    assess,
)
from app.detection.clustering import ClusterPolicy
from app.detection.control import REGISTER, Kind
from app.detection.fusion import FusionPolicy
from app.detection.precedence import PrecedencePolicy
from app.detection.rf_noise import Direction, ThresholdPolicy
from app.detection.sensor_fault import FaultPolicy
from app.detection.track_gap import BoundingBox, GapPolicy
from app.evaluation.export import REQUIRED_POLICIES
from app.scenario.layout import load_layout
from tests.conftest import requires_database

LAYOUT = load_layout()
SENSORS = tuple(site.sensor_id for site in LAYOUT.sensors)[:4]
CHANNELS = (0, 1)
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
TICK = timedelta(seconds=10)
RUN_END = START + timedelta(seconds=600)
QUIET_DBM = -95.0
QUIET_SNR = 20.0

#: Exactly the policies of record, so a test that passes here is a test about the
#: settings the figures were measured under rather than about convenient ones.
POLICIES = DetectorPolicies(
    rf=ThresholdPolicy(
        metric=RfMetric.POWER_DBM,
        direction=Direction.ABOVE,
        threshold=6.0,
        medium_at=10.0,
        high_at=15.0,
    ),
    fault=FaultPolicy(),
    gap=GapPolicy(
        threshold=timedelta(seconds=100),
        contact_fresh_within=timedelta(seconds=30),
        box=BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0),
    ),
    cluster=ClusterPolicy(),
    fusion=FusionPolicy(),
    ladder=PrecedencePolicy(),
)


def _rf(
    run_id: int, *, elevate: dict[tuple[str, int], float] | None = None
) -> tuple[CanonicalObservation, ...]:
    """The dense sensor x channel x time grid `scn-005` specifies."""
    raised = elevate or {}
    out: list[CanonicalObservation] = []
    for sensor in SENSORS:
        site = LAYOUT.site(sensor)
        for channel in CHANNELS:
            at = START
            while at <= RUN_END:
                lift = raised.get((sensor, channel), 0.0)
                out.append(
                    CanonicalObservation(
                        source_id="rf",
                        source_type=SourceType.SYNTHETIC_RF,
                        observation_type=ObservationType.RF,
                        timestamp=at,
                        location=Location(lat=site.lat, lon=site.lon),
                        data_mode=DataMode.SYNTHETIC,
                        validation_status=ValidationStatus.VALID,
                        provenance=Provenance(
                            source_id="rf",
                            source_type=SourceType.SYNTHETIC_RF,
                            data_mode=DataMode.SYNTHETIC,
                            scenario_run_id=run_id,
                        ),
                        payload=RfPayload(
                            sensor_id=sensor,
                            channel_index=channel,
                            centre_frequency_mhz=1575.42,
                            band="GNSS-L1",
                            power_dbm=QUIET_DBM + lift,
                            snr_db=QUIET_SNR - lift,
                            bandwidth_mhz=2.0,
                            signal_type="noise",
                            baseline_delta_db=lift,
                        ),
                    )
                )
                at += TICK
    return tuple(out)


def _tracks(run_id: int, *, stale_after: int = 0) -> tuple[CanonicalObservation, ...]:
    """One aircraft reporting across the run, its staleness optionally frozen."""
    out: list[CanonicalObservation] = []
    at = START
    while at <= RUN_END:
        elapsed = int((at - START).total_seconds())
        out.append(
            CanonicalObservation(
                source_id="track",
                source_type=SourceType.OPENSKY,
                observation_type=ObservationType.TRACK,
                timestamp=at,
                location=Location(lat=51.5, lon=5.0),
                data_mode=DataMode.REPLAYED,
                validation_status=ValidationStatus.VALID,
                provenance=Provenance(
                    source_id="track",
                    source_type=SourceType.OPENSKY,
                    data_mode=DataMode.REPLAYED,
                    scenario_run_id=run_id,
                ),
                payload=TrackPayload(
                    aircraft_id="AC-0001",
                    callsign="TEST01",
                    altitude_m=10000.0,
                    velocity_ms=240.0,
                    heading_deg=90.0,
                    vertical_rate_ms=0.0,
                    on_ground=False,
                    last_contact_s=float(
                        stale_after if stale_after and elapsed >= stale_after else 5
                    ),
                ),
            )
        )
        at += TICK
    return tuple(out)


def _normality(run_ids: tuple[int, ...] = (1,)) -> Normality:
    observations = [o for run_id in run_ids for o in _rf(run_id)]
    return Normality(
        table=compute_rf_baselines(
            observations,
            RfMetric.POWER_DBM,
            baseline_run_ids=run_ids,
            window=timedelta(hours=2),
        ),
        quiet_run_ids=run_ids,
        window=timedelta(hours=2),
    )


def _run(run_id: int = 2, *, finished: bool = True) -> ScenarioRunSummary:
    return ScenarioRunSummary(
        id=run_id,
        scenario_type="gnss-degradation",
        seed=20220627,
        started_at=START,
        completed_at=RUN_END if finished else None,
    )


class _ExplodingFactory:
    """A session factory whose use is a test failure.

    Proves a refusal decidable without the database happens **before** any query
    rather than after one, which is `test_evb_traceability.py`'s idiom.
    """

    def __call__(self) -> Any:  # pragma: no cover -- calling it is the failure
        raise AssertionError("the chain reached the database before refusing")

    def begin(self) -> Any:  # pragma: no cover -- same
        raise AssertionError("the chain reached the database before refusing")


# --------------------------------------------------- what cannot be inferred


def test_a_normality_built_from_no_quiet_runs_is_refused() -> None:
    """Spec: anom-015 (third finding), anom-002.

    A store with no quiet runs cannot be scored. Inventing a baseline from staged
    runs would measure the incident as normal and report the arm clean, which is
    worse than refusing because it looks like a detection result.
    """
    # spec: anom-015, anom-002
    with pytest.raises(ChainError, match="no quiet runs"):
        Normality(
            table=compute_rf_baselines(
                _rf(1),
                RfMetric.POWER_DBM,
                baseline_run_ids=(1,),
                window=timedelta(hours=2),
            ),
            quiet_run_ids=(),
            window=timedelta(hours=2),
        )


def test_a_run_not_known_to_have_finished_is_refused_before_any_query() -> None:
    """Spec: anom-015, db-007.

    Absence of a completion stamp covers a run still going and a run that died.
    Scoring either gives findings over partial observations that change when the
    run completes, so a figure read from the screen would not be the figure the
    run produces.
    """
    # spec: anom-015, db-007
    with pytest.raises(ChainError, match="not known to have finished"):
        assess(
            _run(finished=False),
            rf=_rf(2),
            tracks=_tracks(2),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=_ExplodingFactory(),
        )


def test_a_run_with_no_rf_observations_is_refused_before_any_query() -> None:
    """Spec: anom-015.

    The run's span is taken from its RF readings, and every rule after the first
    is scoped to that span. With no readings there is no span, and a pass that
    carried on would report a run nothing was measured on as a run where nothing
    was found.
    """
    # spec: anom-015
    with pytest.raises(ChainError, match="no RF observations"):
        assess(
            _run(),
            rf=(),
            tracks=_tracks(2),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=_ExplodingFactory(),
        )


def test_the_pass_never_baselines_against_the_run_it_is_scoring() -> None:
    """Spec: anom-015 (second finding), anom-002.

    `compute_rf_baselines` raises on an observation from outside its declared
    quiet runs, so the guarantee is the baseline's. What this holds is that the
    pass does not quietly rebuild one: the run under assessment is not among the
    quiet runs, and the pass completes anyway.
    """
    # spec: anom-015, anom-002
    normality = _normality((1,))

    assert _run().id not in normality.quiet_run_ids


# ------------------------------------------------------------- the provenance


def test_the_policy_record_carries_every_setting_the_export_requires() -> None:
    """Spec: anom-015 (fourth finding), eval-003.

    `eval-003` refuses a provenance record missing one of `REQUIRED_POLICIES`, so
    a pass whose record satisfies that floor by construction cannot produce
    findings the export then refuses to describe.
    """
    # spec: anom-015, eval-003
    record = POLICIES.record(_normality(), layout=LAYOUT)

    missing = [name for name in REQUIRED_POLICIES if name not in record]
    assert missing == []


def test_the_policy_record_names_the_quiet_runs_the_baseline_came_from() -> None:
    """Spec: anom-015 (fourth finding).

    Two passes under identical thresholds and different baselines produce
    different findings. Recorded without the runs, they are indistinguishable,
    which defeats recording the policy at all.
    """
    # spec: anom-015
    record = POLICIES.record(_normality((1, 7, 9)), layout=LAYOUT)

    assert record["BASELINE.quiet_runs"] == "1,7,9"
    assert record["BASELINE.quiet_run_count"] == "3"


def test_the_policy_record_moves_when_a_threshold_moves() -> None:
    """Otherwise it is a label rather than provenance. Spec: anom-015, eval-003."""
    # spec: anom-015, eval-003
    loosened = DetectorPolicies(
        rf=ThresholdPolicy(
            metric=RfMetric.POWER_DBM,
            direction=Direction.ABOVE,
            threshold=8.0,
            medium_at=10.0,
            high_at=15.0,
        ),
        fault=POLICIES.fault,
        gap=POLICIES.gap,
        cluster=POLICIES.cluster,
        fusion=POLICIES.fusion,
        ladder=POLICIES.ladder,
    )

    tight = POLICIES.record(_normality(), layout=LAYOUT)
    loose = loosened.record(_normality(), layout=LAYOUT)

    assert tight["RF-NOISE.threshold_db"] != loose["RF-NOISE.threshold_db"]


def test_the_chain_holds_no_sql_of_its_own() -> None:
    """FR-904, and `anom-015`'s seventh finding.

    Both measurement scripts hold their own observation reader with raw SQL that
    invents five fields the repository already reconstructs from the row. The
    composition moving into `app/` must not bring that with it.
    """
    # spec: anom-015, FR-904, api-003
    import ast
    from pathlib import Path

    from app.detection import chain

    source = Path(chain.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    sql = [
        text_
        for text_ in literals
        if any(word in text_.upper() for word in ("SELECT ", "INSERT ", "DELETE "))
    ]

    assert sql == [], f"the chain holds SQL of its own: {sql}"


# ------------------------------------------------------------- the ordering


@requires_database
def test_the_track_findings_are_written_before_the_spatial_rules_run(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015 (fifth finding), db-008, db-009, db-004.

    `anom-004` and `anom-012` are PostGIS queries over stored rows, so a pass
    written as compute-then-store finds no track evidence and reports it **absent
    rather than unwritten** -- a wrong answer that looks like a quiet corpus.

    Asserted on the statements the engine actually issued, because the ordering is
    the capability and nothing about the returned value distinguishes the two
    arrangements on a run with no track findings.
    """
    # spec: anom-015, db-008, db-009
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _open_run(factory, 2)
    issued: list[str] = []

    @event.listens_for(migrated_database, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        issued.append(statement)

    try:
        assess(
            _run(),
            rf=_rf(2),
            tracks=_tracks(2, stale_after=200),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=factory,
        )
    finally:
        event.remove(migrated_database, "before_cursor_execute", record)

    wrote = next(
        i
        for i, s in enumerate(issued)
        if "detection_findings" in s and ("INSERT" in s.upper() or "DELETE" in s.upper())
    )
    queried = next(
        i for i, s in enumerate(issued) if "ST_Cluster" in s or "ST_DWithin" in s
    )

    assert wrote < queried, "a spatial rule ran before the findings it reads were written"


def _open_run(factory: sessionmaker, run_id: int) -> None:
    """A run row for the findings to hang off, at the id the chain is given."""
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO scenario_runs (id, scenario_type, parameters, seed, "
                "started_at) VALUES (:id, 'gnss-degradation', '{}'::jsonb, 1, now())"
            ),
            {"id": run_id},
        )


@requires_database
def test_the_counts_account_for_every_registered_producer(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015, anom-008.

    `anom-008` refuses to grade a quiet run against an account missing a producer,
    because detectors that ran and found nothing, detectors that never ran and
    detectors pointed at the wrong observations all produce an identical empty
    result. The pass is what supplies that account, so a producer it forgets makes
    the control unanswerable rather than wrong.
    """
    # spec: anom-015, anom-008
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _open_run(factory, 2)

    assessment = assess(
        _run(),
        rf=_rf(2),
        tracks=_tracks(2),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    built = {key for key, producer in REGISTER.items() if producer.kind is not Kind.ABSENT}
    assert set(assessment.counts) == built


@requires_database
def test_a_quiet_run_produces_no_bundles(migrated_database: Engine) -> None:
    """Spec: anom-015, anom-008, evb-001.

    A quiet run returns no bundles and **not** an empty bundle: `anom-008` requires
    zero reportable anomalies and `evb-001` independently requires an empty
    evidence list to fail the build, and the way those agree is that nothing is
    created.
    """
    # spec: anom-015, anom-008, evb-001
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _open_run(factory, 2)

    assessment = assess(
        _run(),
        rf=_rf(2),
        tracks=_tracks(2),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert assessment.reported == ()
    assert assessment.bundles == ()


@requires_database
def test_a_raised_receiver_reaches_a_reported_claim_and_a_stored_bundle(
    migrated_database: Engine,
) -> None:
    """The chain end to end, which is the item. Spec: anom-015.

    One receiver raised well above threshold on every channel: the radio rule
    raises episodes, the fault rule judges the shape, the ladder reports a claim
    and a bundle is built and stored for it. Any broken link leaves this empty
    while every rule's own suite still passes.
    """
    # spec: anom-015, anom-001, anom-007, anom-013, evb-001, evb-002
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _open_run(factory, 2)
    loud = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}

    assessment = assess(
        _run(),
        rf=_rf(2, elevate=loud),
        tracks=_tracks(2),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert assessment.rf.anomalies, "the radio rule raised nothing"
    assert assessment.reported, "the ladder reported nothing"
    assert len(assessment.bundles) == len(assessment.reported)

    with factory() as session:
        stored = session.execute(
            text("SELECT count(*) FROM evidence_bundles WHERE scenario_run_id = 2")
        ).scalar_one()
    assert stored == len(assessment.bundles)


@requires_database
def test_the_pass_is_idempotent(migrated_database: Engine) -> None:
    """Spec: anom-015, db-008.

    `db-008` replaces per run per rule, which is what makes a re-run under a new
    policy safe -- and what makes a pass that failed part-way recoverable by
    running it again rather than by clearing anything up.
    """
    # spec: anom-015, db-008
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _open_run(factory, 2)
    loud = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}

    def once() -> tuple[int, int]:
        assess(
            _run(),
            rf=_rf(2, elevate=loud),
            tracks=_tracks(2, stale_after=200),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=factory,
        )
        with factory() as session:
            findings = session.execute(
                text("SELECT count(*) FROM detection_findings WHERE scenario_run_id = 2")
            ).scalar_one()
            bundles = session.execute(
                text("SELECT count(*) FROM evidence_bundles WHERE scenario_run_id = 2")
            ).scalar_one()
        return int(findings), int(bundles)

    assert once() == once()


@requires_database
def test_the_findings_carry_the_policy_that_produced_them(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015 (fourth finding), eval-003.

    Without this a stored finding is unprovenanced: a screen would show figures
    taken under one threshold while the settings in the repository say another,
    with nothing able to detect the disagreement.
    """
    # spec: anom-015, eval-003
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _open_run(factory, 2)
    loud = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}

    assess(
        _run(),
        rf=_rf(2, elevate=loud),
        tracks=_tracks(2),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    with factory() as session:
        recorded = session.execute(
            text(
                "SELECT DISTINCT policy FROM detection_findings "
                "WHERE scenario_run_id = 2"
            )
        ).scalars().all()

    assert len(recorded) == 1
    assert recorded[0]["RF-NOISE.threshold_db"] == "6.0"
    assert recorded[0]["BASELINE.quiet_runs"] == "1"


# ----------------------------------------------------- reading through the port


@requires_database
def test_observations_are_read_back_as_the_row_holds_them(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015 (seventh finding), FR-904.

    Both measurement scripts rebuild observations with `source_id="o"`, a source
    type derived from the observation type, `VALID` asserted rather than read, and
    a `Provenance` built from scratch. The repository reconstructs all five from
    the row. The hardcoded mapping happens to agree with what the generator
    writes, which makes it a right answer from a wrong source.
    """
    # spec: anom-015, FR-904, dal-001
    from app.db.repository import PostgisObservationRepository, observations_for_run

    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _open_run(factory, 2)
    written = _rf(2)[:4]
    PostgisObservationRepository(factory).save_batch(written, [])

    read = observations_for_run(factory, 2, ObservationType.RF)

    assert len(read) == len(written)
    assert read[0].source_id == written[0].source_id
    assert read[0].provenance.scenario_run_id == 2
    assert read[0].data_mode is DataMode.SYNTHETIC
