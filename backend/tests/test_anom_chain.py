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
from app.db.findings import findings_for_run
from app.db.repository import (
    PostgisObservationRepository,
    detection_pass_for_run,
    observations_for_run,
)
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.chain import (
    Assessment,
    Bid,
    ChainError,
    DetectorPolicies,
    Normality,
    assess,
    reported_findings,
)
from app.detection.clustering import ClusterPolicy
from app.detection.control import REGISTER
from app.detection.findings import DetectionFinding
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE_TYPE
from app.detection.fusion import RULE_ID as FUSION_RULE
from app.detection.fusion import Declination, FusionPolicy, InterferenceFindings
from app.detection.precedence import Claim, PrecedencePolicy, Resolution, Zone
from app.detection.rate_excess import FINDING_TYPE as EXCESS_TYPE
from app.detection.rf_noise import Direction, RfNoiseFindings, ThresholdPolicy
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT_TYPE
from app.detection.sensor_fault import RULE_ID as FAULT_RULE
from app.detection.sensor_fault import FaultPolicy, SensorFaultFindings
from app.detection.track_gap import RULE_ID as GAP_RULE
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
                # The two staleness fields are different measurements and
                # `anom-010` reads both: fresh contact with a stale *position* is
                # the frozen-position mechanism, which is what `stale_after`
                # stages here. Both stale would be the suppression mechanism.
                payload=TrackPayload(
                    aircraft_id="AC-0001",
                    flight_id="TEST01",
                    altitude_m=10000.0,
                    velocity_ms=240.0,
                    heading_deg=90.0,
                    vertical_rate_ms=0.0,
                    on_ground=False,
                    position_staleness_s=float(
                        elapsed - stale_after
                        if stale_after and elapsed >= stale_after
                        else 5
                    ),
                    contact_staleness_s=5.0,
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
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=_ExplodingFactory(),
        )


@requires_database
def test_a_run_with_no_rf_observations_is_refused_before_any_write(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015.

    The run's span is taken from its RF readings, and every rule after the first
    is scoped to that span. With no readings there is no span, and a pass that
    carried on would report a run nothing was measured on as a run where nothing
    was found.

    Database tier rather than unit, and the reason is the correction the suite
    forced: the pass reads its own observations, so *whether there are any* is
    knowable only after reading. The property that survives is the one that
    matters -- the refusal still precedes every write.
    """
    # spec: anom-015
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, 2, rf=False)

    with pytest.raises(ChainError, match="no RF observations"):
        assess(
            _run(),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=factory,
        )

    with factory() as session:
        written = session.execute(
            text("SELECT count(*) FROM detection_findings WHERE scenario_run_id = 2")
        ).scalar_one()
    assert written == 0, "a refused pass wrote findings"


@requires_database
def test_the_pass_reads_the_run_it_was_given(migrated_database: Engine) -> None:
    """Spec: anom-015, and the reason observations are not a parameter.

    Taking them as values made `assess(run 7, observations of run 9)`
    representable, and the only thing that caught it was a citation resolution at
    the very end -- after run 7's findings had been written from run 9's data. With
    the read inside, a loud receiver on another run cannot reach this one's claims.
    """
    # spec: anom-015, evb-002
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, 2)
    _store(factory, 3, elevate={(SENSORS[0], channel): 20.0 for channel in CHANNELS})

    quiet = assess(
        _run(2),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert quiet.rf.anomalies == ()
    assert quiet.reported == ()


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

    # And the values, not only the keys. A record carrying every required name
    # with a wrong value against each is worse than an incomplete one: it reads
    # as provenance and resolves to settings nothing ran under.
    assert record["RF-NOISE.threshold_db"] == "6.0"
    assert record["RF-NOISE.metric"] == "power_dbm"
    assert record["TRACK-GAP.threshold_s"] == "100.0"
    assert record["TRACK-GAP.box"] == "49.0,54.0,3.0,11.0"
    assert record["BASELINE.window_h"] == "2.0"


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
    _store(factory, 2, stale_after=200)
    issued: list[str] = []

    @event.listens_for(migrated_database, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        issued.append(f"{statement} -- {parameters}")

    try:
        assessment = assess(
            _run(),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=factory,
        )
    finally:
        event.remove(migrated_database, "before_cursor_execute", record)

    # Named by **rule**, not only by table. The mutation pass found the first
    # version of this assertion worthless: it looked for any write to
    # `detection_findings`, and with the track write removed the *radio* write
    # still preceded the query -- so the one mutant this test exists to catch
    # passed it.
    wrote = next(
        i
        for i, s in enumerate(issued)
        if "detection_findings" in s
        and GAP_RULE in s
        and ("INSERT" in s.upper() or "DELETE" in s.upper())
    )
    queried = next(
        i for i, s in enumerate(issued) if "ST_Cluster" in s or "ST_DWithin" in s
    )

    assert (
        wrote < queried
    ), "a spatial rule ran before the findings it reads were written"
    # And the consequence, which is what makes the order load-bearing rather than
    # a preference: the clustering rule sees only rows that are already down.
    assert assessment.gaps, "the staged gap was not found at all"
    assert (
        assessment.clusters
    ), "the spatial rule saw none of the findings written for it"


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


def _store(
    factory: sessionmaker,
    run_id: int,
    *,
    elevate: dict[tuple[str, int], float] | None = None,
    stale_after: int = 0,
    rf: bool = True,
) -> None:
    """A run and its observations, where the pass will read them from.

    The pass reads its own run rather than taking observations as values, because
    the bundles it stores are resolved against these rows -- so the values the
    rules reason from and the rows the citations resolve against are one thing by
    construction rather than by the caller's care.
    """
    _open_run(factory, run_id)
    observations = [
        *(_rf(run_id, elevate=elevate) if rf else ()),
        *_tracks(run_id, stale_after=stale_after),
    ]
    PostgisObservationRepository(factory).save_batch(observations, [])


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
    _store(factory, 2)

    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    # `built` on the register, not a count: `anom-006` is registered as **not
    # exercised** rather than clean, because reporting zero of a type across
    # twenty quiet runs quotes the absence of a rule as the accuracy of one.
    built = {key for key, producer in REGISTER.items() if producer.built}
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
    _store(factory, 2)

    assessment = assess(
        _run(),
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
    loud = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}
    _store(factory, 2, elevate=loud, stale_after=200)

    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert assessment.rf.anomalies, "the radio rule raised nothing"
    assert assessment.reported, "the ladder reported nothing"
    assert len(assessment.bundles) == len(assessment.reported)

    # Built and **not** stored. The line is between what is regenerable and id-free
    # and what carries identity something else cites: `eval-004`'s pre-registered
    # sample names its twenty bundles by id, so a pass that rebuilt them corpus-wide
    # would renumber that population and stop the draw reproducing itself.
    with factory() as session:
        stored = session.execute(
            text("SELECT count(*) FROM evidence_bundles WHERE scenario_run_id = 2")
        ).scalar_one()
    assert stored == 0, "the pass stored bundles a caller did not ask it to store"


@requires_database
def test_the_pass_is_idempotent(migrated_database: Engine) -> None:
    """Spec: anom-015, db-008.

    `db-008` replaces per run per rule, which is what makes a re-run under a new
    policy safe -- and what makes a pass that failed part-way recoverable by
    running it again rather than by clearing anything up.
    """
    # spec: anom-015, db-008
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    loud = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}
    _store(factory, 2, elevate=loud, stale_after=200)

    def once() -> tuple[int, int]:
        assess(
            _run(),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=factory,
        )
        with factory() as session:
            findings = session.execute(
                text(
                    "SELECT count(*) FROM detection_findings WHERE scenario_run_id = 2"
                )
            ).scalar_one()
            bundles = session.execute(
                text("SELECT count(*) FROM evidence_bundles WHERE scenario_run_id = 2")
            ).scalar_one()
        return int(findings), int(bundles)

    assert once() == once()


@requires_database
def test_storing_the_bundles_is_the_callers_call(migrated_database: Engine) -> None:
    """The other half of the line. Spec: anom-015, evb-002, eval-004.

    A caller with no pre-registered population to protect stores what the pass
    built, and the bundles resolve against the same rows the pass read -- which is
    why the pass reads its own run rather than taking observations as values.
    """
    # spec: anom-015, evb-002
    from app.db.bundles import save_bundles

    factory = sessionmaker(bind=migrated_database, autoflush=False)
    loud = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}
    _store(factory, 2, elevate=loud)
    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    save_bundles(factory, scenario_run_id=2, bundles=assessment.bundles)

    with factory() as session:
        stored = session.execute(
            text("SELECT count(*) FROM evidence_bundles WHERE scenario_run_id = 2")
        ).scalar_one()
    assert stored == len(assessment.bundles) > 0


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
    loud = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}
    _store(factory, 2, elevate=loud, stale_after=200)

    assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    with factory() as session:
        recorded = (
            session.execute(
                text(
                    "SELECT DISTINCT policy FROM detection_findings "
                    "WHERE scenario_run_id = 2"
                )
            )
            .scalars()
            .all()
        )

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
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _open_run(factory, 2)
    written = _rf(2)[:4]
    PostgisObservationRepository(factory).save_batch(written, [])

    read = observations_for_run(factory, 2, ObservationType.RF)

    assert len(read) == len(written)
    assert read[0].source_id == written[0].source_id
    assert read[0].provenance.scenario_run_id == 2
    assert read[0].data_mode is DataMode.SYNTHETIC


# ---------------------------------------------- the receivers behind a claim


@requires_database
def test_each_claim_keeps_the_receivers_its_evidence_rested_on(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015, anom-009.

    No claim carries them -- the rules retain derived evidence on purpose, so a
    fault cannot say when its own evidence matured -- and `anom-009`'s registry
    states a **count of receivers** rather than a formula. The pass is the only
    place both halves are in view, so a pass that dropped them would make latency
    unmeasurable from its own output.
    """
    # spec: anom-015, anom-009
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    loud = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}
    _store(factory, 2, elevate=loud)

    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert assessment.reported
    for claim in assessment.reported:
        assert assessment.receivers_for(claim), "a reported claim has no receivers"
    assert SENSORS[0] in assessment.receivers_for(assessment.reported[0])


@requires_database
def test_a_claim_this_pass_did_not_make_is_refused(migrated_database: Engine) -> None:
    """Spec: anom-015, anom-009.

    Returning an empty tuple would let `anom-009` measure an interference zone's
    latency from whichever receiver began first, understating it by however long
    they were staggered -- silently, since the figure still looks like a latency.
    """
    # spec: anom-015, anom-009
    from app.detection.precedence import Claim

    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, 2)
    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )
    stranger = Claim(
        rule_id="SENSOR-FAULT",
        anomaly_type="possible_sensor_fault",
        zone=LAYOUT.sensors[0],
    )

    with pytest.raises(ChainError, match="no receivers recorded"):
        assessment.receivers_for(stranger)  # type: ignore[arg-type]


# ------------------------------------------- the account, over crafted inputs
#
# Constructed rather than assessed, and the mutation pass is the reason. Every
# database-tier test above produces exactly **one** claim and nothing suppressed,
# which made four separate mutants invisible: counting bids instead of reported
# claims, counting every claim as a fault, dropping the declined zones, and taking
# a zone's first receiver for all of them. `anom-009` recorded the same shape --
# every test had given a rule exactly as many receivers as it required, making
# "the second to qualify" and "the last" indistinguishable on a corpus that
# carries three-receiver zones.


def _zone(sensor: str = "RF-01") -> Zone:
    site = LAYOUT.site(sensor)
    return Zone(
        centre=Location(lat=site.lat, lon=site.lon),
        started_at=START,
        ended_at=RUN_END,
    )


def _assessment(
    *,
    reported: tuple[Claim, ...],
    bids: tuple[Bid, ...],
    zones: tuple[object, ...] = (),
    declined: tuple[Declination, ...] = (),
) -> Assessment:
    return Assessment(
        scenario_run_id=2,
        rf=RfNoiseFindings(),
        faults=SensorFaultFindings(),
        gaps=(),
        clusters=(),
        interference=InterferenceFindings(zones=zones, declined=declined),  # type: ignore[arg-type]
        resolution=Resolution(reported=reported),
        bids=bids,
        bundles=(),
        policy={},
    )


def test_the_account_counts_reported_claims_and_not_every_bid() -> None:
    """Spec: anom-015, anom-008, anom-013.

    A bid the ladder suppressed is a *competing conclusion*, never an answer the
    analyst was given, so counting it would tell `anom-008` a quiet run showed
    something. `evb-001` makes the same distinction when it carries a suppressed
    claim in `superseded` and never in the evidence list: co-occurrence read as
    concurrence inverts the truth exactly.
    """
    # spec: anom-015, anom-008, anom-013
    won = Claim(rule_id=FAULT_RULE, anomaly_type=FAULT_TYPE, zone=_zone())
    lost = Claim(
        rule_id=FUSION_RULE, anomaly_type=INTERFERENCE_TYPE, zone=_zone("RF-02")
    )

    counts = _assessment(
        reported=(won,),
        bids=(Bid(claim=won, sensors=("RF-01",)), Bid(claim=lost, sensors=("RF-02",))),
    ).counts

    assert counts[(FAULT_RULE, FAULT_TYPE)] == 1
    assert counts[(FUSION_RULE, INTERFERENCE_TYPE)] == 0


def test_the_account_counts_each_type_as_its_own_type() -> None:
    """Spec: anom-015, anom-008.

    A count that read "how many claims" rather than "how many of this type" is
    right on every run carrying one claim, which is most of them, and wrong on
    exactly the runs where the ladder had a contest to decide.
    """
    # spec: anom-015, anom-008
    zone_claim = Claim(
        rule_id=FUSION_RULE, anomaly_type=INTERFERENCE_TYPE, zone=_zone()
    )

    counts = _assessment(
        reported=(zone_claim,), bids=(Bid(claim=zone_claim, sensors=("RF-01",)),)
    ).counts

    assert counts[(FUSION_RULE, INTERFERENCE_TYPE)] == 1
    assert counts[(FAULT_RULE, FAULT_TYPE)] == 0


def test_the_rate_excess_count_includes_what_it_declined_to_measure() -> None:
    """Spec: anom-015, anom-008, anom-012.

    47 of 61 zones on the real corpus cannot be measured at all: a period holding
    no findings has a rate consisting of nothing but the smoothing constant. A
    count omitting them would tell `anom-008` the rule did not look, when it
    looked and could not decide -- which is the one distinction that control exists
    to protect.
    """
    # spec: anom-015, anom-008, anom-012
    declined = (
        Declination(
            sensors=("RF-01",),
            started_at=START,
            ended_at=RUN_END,
            reason="not measurable",
        ),
    )

    counts = _assessment(reported=(), bids=(), declined=declined).counts

    assert counts[(GAP_RULE, EXCESS_TYPE)] == 1


def test_receivers_are_matched_to_their_own_claim() -> None:
    """Spec: anom-015, anom-009.

    With one claim in play, "this claim's receivers" and "the first bid's
    receivers" are the same answer -- which is what let a mutant returning the
    first bid unconditionally survive. Two claims is the smallest case that tells
    them apart, and the real corpus carries three-receiver zones.
    """
    # spec: anom-015, anom-009
    fault = Claim(rule_id=FAULT_RULE, anomaly_type=FAULT_TYPE, zone=_zone("RF-01"))
    zone = Claim(
        rule_id=FUSION_RULE, anomaly_type=INTERFERENCE_TYPE, zone=_zone("RF-02")
    )
    assessment = _assessment(
        reported=(fault, zone),
        bids=(
            Bid(claim=fault, sensors=("RF-01",)),
            Bid(claim=zone, sensors=("RF-02", "RF-03")),
        ),
    )

    assert assessment.receivers_for(fault) == ("RF-01",)
    assert assessment.receivers_for(zone) == ("RF-02", "RF-03")


@requires_database
def test_receivers_deviating_together_all_reach_the_claim(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015, anom-005, anom-009.

    Every receiver raised through the same window is `anom-007`'s *environmental*
    verdict -- more than one deviated together -- which is what `anom-005` consumes.
    The claim's window is then the **union** of its receivers', so dropping any of
    them understates the latency by however long they were staggered, silently,
    because the figure still looks like a latency.
    """
    # spec: anom-015, anom-005, anom-009
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    everywhere = {(sensor, channel): 20.0 for sensor in SENSORS for channel in CHANNELS}
    _store(factory, 2, elevate=everywhere)

    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert assessment.reported, "nothing reached a claim with every receiver raised"
    carried = {
        sensor
        for claim in assessment.reported
        for sensor in assessment.receivers_for(claim)
    }
    assert len(carried) > 1, (
        f"a claim over several receivers kept only {sorted(carried)}: anom-005's "
        "window is the union of its receivers', so a subset understates latency"
    )


# ------------------------------------------- the conclusions, and that it ran
#
# Added 2026-10-02 with `anom-015`'s second amendment. The pass persisted its
# *evidence* and not its *conclusions*: the two rules at the end of the ladder
# returned their claims on the `Assessment` and wrote nowhere, which inside one
# process is invisible and from a web request means they do not exist. And
# nothing recorded that a pass had happened at all, so a run examined and found
# clean left exactly what a run nobody examined left.


def _finding(subject: str, *, rule_id: str = FAULT_RULE) -> DetectionFinding:
    site = LAYOUT.site(SENSORS[0])
    return DetectionFinding(
        scenario_run_id=2,
        rule_id=rule_id,
        finding_type=FAULT_TYPE if rule_id == FAULT_RULE else INTERFERENCE_TYPE,
        subject=subject,
        started_at=START,
        ended_at=RUN_END,
        location=Location(lat=site.lat, lon=site.lon),
        details={"confidence": "high"},
    )


def test_only_the_claims_the_ladder_reported_are_written() -> None:
    """Spec: anom-015, anom-013, evb-001.

    A suppressed claim is a competing conclusion and not a second event. Stored
    beside the claim that beat it, every count taken over the table reads two
    events where there was one -- which is `evb-001`'s reason for carrying a
    suppressed claim in `superseded` and never in the evidence list.
    """
    # spec: anom-015, anom-013
    won = Claim(rule_id=FAULT_RULE, anomaly_type=FAULT_TYPE, zone=_zone())
    lost = Claim(
        rule_id=FUSION_RULE, anomaly_type=INTERFERENCE_TYPE, zone=_zone("RF-02")
    )

    written = reported_findings(
        Resolution(reported=(won,)),
        evidence=(
            (won, _finding("RF-01")),
            (lost, _finding("RF-02", rule_id=FUSION_RULE)),
        ),
    )

    assert [f.subject for f in written] == ["RF-01"]


def test_a_claim_is_matched_to_its_finding_on_identity() -> None:
    """Spec: anom-015, and `receivers_for`'s own rule one function along.

    Two claims of one rule over one zone are **equal by value** -- a frozen
    dataclass of a rule id, a type and a zone -- so a membership test writes the
    finding of a claim the ladder never reported. The ladder passes claims
    through unchanged, so the object reported is the object bid, and identity is
    the only comparison that distinguishes them.
    """
    # spec: anom-015, anom-013
    reported = Claim(rule_id=FAULT_RULE, anomaly_type=FAULT_TYPE, zone=_zone())
    twin = Claim(rule_id=FAULT_RULE, anomaly_type=FAULT_TYPE, zone=_zone())
    assert reported == twin and reported is not twin

    written = reported_findings(
        Resolution(reported=(reported,)),
        evidence=((reported, _finding("RF-01")), (twin, _finding("RF-07"))),
    )

    assert [f.subject for f in written] == ["RF-01"]


def test_the_rules_the_pass_persists_are_the_rules_the_endpoint_claims() -> None:
    """Spec: anom-015, api-012, anom-008.

    `api-012` reports two registered producers as *not persisted* -- `anom-004`'s
    clusters, whose citation shape `evb-002` refuses by name, and `anom-012`'s
    rate excess, which is internal to the fusion decision. That is a second
    declaration of what this pass writes, and a declaration that cannot drift is
    worth more than one that is merely correct today: a rule which starts
    persisting its output must not leave the endpoint reporting it unpersisted.

    Read off the calls rather than matched as text, on `db-006`'s rule: a
    substring search is satisfied by the rule id appearing in this module's prose,
    which it does, several times.
    """
    # spec: anom-015, api-012, db-006
    import ast
    from pathlib import Path

    from app.api.v1.schemas.operational_picture import PERSISTED_PRODUCERS
    from app.detection import chain

    tree = ast.parse(Path(chain.__file__).read_text(encoding="utf-8"))
    named = [
        keyword.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "save_findings"
        for keyword in node.keywords
        if keyword.arg == "rule_id" and isinstance(keyword.value, ast.Name)
    ]

    assert named, "no save_findings call names a rule id"
    assert {getattr(chain, name) for name in named} == {
        rule_id for rule_id, _ in PERSISTED_PRODUCERS
    }


@requires_database
def test_a_reported_fault_is_written_as_a_finding(migrated_database: Engine) -> None:
    """Spec: anom-015, db-008, api-012.

    One receiver raised with its neighbours nominal is `anom-007`'s attribution,
    and the ladder reports it. Before this the claim existed only on the returned
    object, so an endpoint in another process had nothing to serve -- and the
    whole chain's purpose is that conclusion.
    """
    # spec: anom-015, db-008, api-012
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, 2, elevate={(SENSORS[0], channel): 20.0 for channel in CHANNELS})

    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert assessment.faults.faults, "the fault rule attributed nothing"
    stored = findings_for_run(factory, 2, rule_id=FAULT_RULE)
    assert [f.subject for f in stored] == [SENSORS[0]]
    assert [f.finding_type for f in stored] == [FAULT_TYPE]
    # The confidence travels in `details`, as `anom-001`'s severity does: it
    # qualifies the attribution and the table has no column for either.
    assert stored[0].details["confidence"] in {"low", "medium", "high"}


@requires_database
def test_a_reported_interference_zone_is_written_as_a_finding(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015, anom-005, db-008, api-012.

    Every receiver raised through one window is the environmental verdict, which
    is what `anom-005` consumes. Its zone spans several receivers, so the row has
    to keep all of them -- the subject names one and `details` names the set,
    because the window is the union of theirs.
    """
    # spec: anom-015, anom-005, api-012
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    everywhere = {(sensor, channel): 20.0 for sensor in SENSORS for channel in CHANNELS}
    _store(factory, 2, elevate=everywhere)

    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert assessment.interference.zones, "no zone was established"
    stored = findings_for_run(factory, 2, rule_id=FUSION_RULE)
    assert stored, "a reported interference zone was not written"
    assert {f.finding_type for f in stored} == {INTERFERENCE_TYPE}
    assert len(stored[0].details["sensors"]) > 1, (
        "a zone row kept one receiver: anom-005's window is the union of its "
        "receivers', so a subset misreports which deviated together"
    )


@requires_database
def test_the_run_is_stamped_with_when_it_was_examined_and_under_what_policy(
    migrated_database: Engine,
) -> None:
    """Spec: anom-015, api-012, eval-003.

    The policy sits beside the stamp and not only on the findings, because a
    quiet run has **no findings to carry it** -- and a quiet run scored under
    thresholds nobody recorded is exactly the case `anom-008`'s measured bands
    were taken under.
    """
    # spec: anom-015, api-012, eval-003
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, 2)

    assessment = assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    recorded = detection_pass_for_run(factory, 2)
    assert recorded is not None, "the pass left no record that it ran"
    assert recorded.policy == dict(assessment.policy)
    assert recorded.at.tzinfo is not None


@requires_database
def test_a_run_the_pass_found_nothing_in_is_still_stamped(
    migrated_database: Engine,
) -> None:
    """The capability, stated as plainly as it can be. Spec: anom-015, anom-008.

    Zero findings is the answer a quiet run gives and the answer a run nobody
    examined gives, and the findings write replaces per run per rule *including
    at zero*, so the table cannot tell them apart. The stamp is the only thing
    that can, which is why it is written whether or not anything was found.
    """
    # spec: anom-015, anom-008, api-012
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, 2)
    _open_run(factory, 3)

    assess(
        _run(2),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )

    assert findings_for_run(factory, 2, rule_id=FAULT_RULE) == []
    assert detection_pass_for_run(factory, 2) is not None, "a clean run was not stamped"
    assert detection_pass_for_run(factory, 3) is None, "an unexamined run was stamped"


@requires_database
def test_the_stamp_is_written_after_every_finding(migrated_database: Engine) -> None:
    """Spec: anom-015.

    A pass that dies midway must leave a run that is **not known to have been
    scored** rather than one claiming an examination it did not finish. Stamped
    first, a crash between the stamp and the last write leaves a run reporting a
    complete pass over a partial set of findings, and nothing can detect it.

    Asserted on the statements the engine issued, because no property of a
    successful pass distinguishes the two orders.
    """
    # spec: anom-015, db-008
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, 2, elevate={(SENSORS[0], channel): 20.0 for channel in CHANNELS})
    issued: list[str] = []

    @event.listens_for(migrated_database, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        issued.append(statement)

    try:
        assess(
            _run(),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=factory,
        )
    finally:
        event.remove(migrated_database, "before_cursor_execute", record)

    stamped = next(
        i for i, s in enumerate(issued) if "detection_pass_at" in s and "UPDATE" in s
    )
    last_write = max(
        i
        for i, s in enumerate(issued)
        if "detection_findings" in s
        and ("INSERT" in s.upper() or "DELETE" in s.upper())
    )

    assert last_write < stamped, "the run was stamped before its findings were written"


@requires_database
def test_a_refused_pass_leaves_the_run_unstamped(migrated_database: Engine) -> None:
    """Spec: anom-015, db-007.

    The two refusals already promise to leave no partial write behind. The stamp
    is the one write whose presence is itself a claim, so a refusal that stamped
    anyway would assert an examination that did not happen.
    """
    # spec: anom-015, db-007
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, 2, rf=False)

    with pytest.raises(ChainError, match="no RF observations"):
        assess(
            _run(),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            session_factory=factory,
        )

    assert detection_pass_for_run(factory, 2) is None
