"""Firing the detection pass when a generation batch completes. Spec: anom-016.

Three groups, and the first two are about things that are true today and written
down nowhere.

**The settings of record live outside the application.** Every detection figure
this project quotes was measured under one set of detector settings, and that set
exists in `measurements/corpus/detection_metrics.py` and in a copy in
`tests/test_anom_chain.py` annotated *exactly the policies of record*. `app/` has
none of them, so a trigger inside the application has nothing to hand the pass and
whatever it declares becomes a third set with the same standing as the other two.
Three copies that have drifted are each internally consistent, so nothing fails --
the screen simply shows figures taken under settings that differ from the ones
every quoted number was measured under. One definition here, plus a **pin**: the
eleven values spelled out in a test, which is not a fourth copy because a
definition is what something runs under and a pin is an assertion about it.

**The two paths differ on purpose, and the mechanism is placement.**
`app/pipeline.py`'s `main()` calls `run_batch` directly; `run_batch_now` calls it
too and is what the screen reaches. Scoring goes in the second, so the command
that built the 300 hours behind every figure cannot stamp them with whatever
settings are current -- `eval-001`'s argument that the corpus and the detector
settings must stay separable or the same hours cannot be re-scored. Asserted in
both directions, because only one direction is a guard: that the corpus command
reaches no detector, and that the interactive path reaches the pass.

**The harness may read the answer key's label; the rules may not.** Choosing which
runs count as quiet means asking which are of the `normal-baseline` kind, and the
kind of a run is the label for what was injected. The selection is the harness's
and what crosses into the detection layer is run **ids** -- `anom-008`'s rule,
`api-009`'s reason. So far that has been a thing done correctly rather than a thing
written down.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
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
    ValidationStatus,
)
from app.db.repository import (
    PostgisObservationRepository,
    detection_pass_for_run,
    quiet_run_ids,
    run_summary,
)
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.chain import ChainError, DetectorPolicies, measure_normality
from app.detection.rf_noise import Direction
from app.detection.settings import (
    BASELINE_WINDOW,
    CORPUS_BOX,
    GAP_POLICY,
    POLICIES_OF_RECORD,
    RF_POLICY,
)
from app.evaluation.export import REQUIRED_POLICIES
from app.pipeline import BatchSummary, RunOutcome
from app.scenario import batch as batch_module
from app.scenario.batch import BatchScoring, score_batch
from app.scenario.layout import load_layout
from tests.conftest import requires_database

BACKEND = Path(__file__).resolve().parents[1]
LAYOUT = load_layout()
SENSORS = tuple(site.sensor_id for site in LAYOUT.sensors)[:4]
CHANNELS = (0, 1)
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
TICK = timedelta(seconds=10)
RUN_END = START + timedelta(seconds=600)
QUIET_DBM = -95.0
QUIET_SNR = 20.0

QUIET = 101
STAGED = (201, 202)


def _rf(run_id: int) -> tuple[CanonicalObservation, ...]:
    """A quiet sensor x channel x time grid, as `scn-005` specifies it."""
    out: list[CanonicalObservation] = []
    for sensor in SENSORS:
        site = LAYOUT.site(sensor)
        for channel in CHANNELS:
            at = START
            while at <= RUN_END:
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
                            power_dbm=QUIET_DBM,
                            snr_db=QUIET_SNR,
                            bandwidth_mhz=2.0,
                            signal_type="noise",
                            baseline_delta_db=0.0,
                        ),
                    )
                )
                at += TICK
    return tuple(out)


def _open_run(
    factory: sessionmaker,
    run_id: int,
    *,
    scenario_type: str = "gnss-degradation",
    finished: bool = True,
) -> None:
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO scenario_runs (id, scenario_type, parameters, seed, "
                "started_at) VALUES (:id, :kind, '{}'::jsonb, 1, now())"
            ),
            {"id": run_id, "kind": scenario_type},
        )
        if finished:
            session.execute(
                text("UPDATE scenario_runs SET completed_at = now() WHERE id = :id"),
                {"id": run_id},
            )


def _store(
    factory: sessionmaker,
    run_id: int,
    *,
    scenario_type: str = "gnss-degradation",
    finished: bool = True,
) -> None:
    _open_run(factory, run_id, scenario_type=scenario_type, finished=finished)
    PostgisObservationRepository(factory).save_batch(list(_rf(run_id)), [])


def _run(run_id: int, *, finished: bool = True) -> ScenarioRunSummary:
    return ScenarioRunSummary(
        id=run_id,
        scenario_type="gnss-degradation",
        seed=20220627,
        started_at=START,
        completed_at=RUN_END if finished else None,
    )


def _outcome(index: int, *, run_id: int | None, completed: bool) -> RunOutcome:
    return RunOutcome(
        index=index,
        seed=20220627 + index,
        scenario_type="gnss-degradation",
        start=START,
        duration_seconds=600,
        run_id=run_id,
        completed=completed,
    )


def _summary(*outcomes: RunOutcome) -> BatchSummary:
    return BatchSummary(
        base_seed=20220627,
        scenario_type="gnss-degradation",
        runs=outcomes,
        seconds=70.0,
    )


class _ExplodingFactory:
    """A session factory whose use is a test failure."""

    def __call__(self) -> Any:  # pragma: no cover -- calling it is the failure
        raise AssertionError("the trigger reached the database before refusing")

    def begin(self) -> Any:  # pragma: no cover -- same
        raise AssertionError("the trigger reached the database before refusing")


class _Recorder:
    """A stand-in for the pass, remembering what it was asked to score."""

    def __init__(self, *, fails: frozenset[int] = frozenset()) -> None:
        self.runs: list[int] = []
        self.normalities: list[object] = []
        self.policies: list[DetectorPolicies] = []
        self.fails = fails

    def assess(
        self,
        run: ScenarioRunSummary,
        *,
        normality: object,
        policies: DetectorPolicies,
        layout: object,
        session_factory: object,
    ) -> object:
        self.runs.append(run.id)
        self.normalities.append(normality)
        self.policies.append(policies)
        if run.id in self.fails:
            raise ChainError(f"refusing run {run.id}")
        return object()


@dataclass
class _Wiring:
    """What the cheap stand-ins saw, so a test can assert on it."""

    baseline: object
    baselines_measured: int = 0


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _Recorder,
    *,
    quiet: tuple[int, ...] = (QUIET,),
) -> _Wiring:
    """Everything `score_batch` composes, replaced by something cheap."""
    wiring = _Wiring(baseline=object())

    def _measure(session_factory: object, **kwargs: Any) -> object:
        wiring.baselines_measured += 1
        if not kwargs["quiet_run_ids"]:
            raise ChainError("a baseline measured over no quiet runs")
        return wiring.baseline

    monkeypatch.setattr(batch_module, "quiet_run_ids", lambda _factory: quiet)
    monkeypatch.setattr(batch_module, "measure_normality", _measure)
    monkeypatch.setattr(
        batch_module, "run_summary", lambda _factory, run_id: _run(run_id)
    )
    monkeypatch.setattr(batch_module, "assess", recorder.assess)
    return wiring


# ------------------------------------------------- the settings of record


def _normality_stub() -> Any:
    from app.detection.chain import Normality

    return Normality(
        table=compute_rf_baselines(
            [],
            RfMetric.POWER_DBM,
            baseline_run_ids=(QUIET,),
            window=BASELINE_WINDOW,
        ),
        quiet_run_ids=(QUIET,),
        window=BASELINE_WINDOW,
    )


def test_the_settings_of_record_are_pinned_value_by_value() -> None:
    # spec: anom-016 -- the pin, and it is deliberately a second statement of
    # the eleven values rather than a derivation of them. Moving them into the
    # application removes the copies and leaves a drift just as silent: someone
    # edits a threshold, every other test still passes, and every figure on
    # record is now quoted under settings that are not the ones in force.
    # These are the values `measurements/corpus/detection_metrics.log`,
    # `track_gap_recall.log` and the whole detection table were measured under.
    assert RF_POLICY.metric is RfMetric.POWER_DBM
    assert RF_POLICY.direction is Direction.ABOVE
    assert RF_POLICY.threshold == 6.0
    assert RF_POLICY.medium_at == 10.0
    assert RF_POLICY.high_at == 15.0

    assert GAP_POLICY.threshold == timedelta(seconds=100)
    assert GAP_POLICY.contact_fresh_within == timedelta(seconds=30)

    assert (CORPUS_BOX.lat_min, CORPUS_BOX.lat_max) == (49.0, 54.0)
    assert (CORPUS_BOX.lon_min, CORPUS_BOX.lon_max) == (3.0, 11.0)
    assert GAP_POLICY.box == CORPUS_BOX

    assert BASELINE_WINDOW == timedelta(hours=2)


def test_the_rest_of_the_record_is_the_defaults_already_in_the_application() -> None:
    # spec: anom-016 -- what is homeless is smaller than it looks, and this is
    # the half of the claim that could rot. Four of the six policy objects are
    # taken at their defaults, so if one of them grows a required field this
    # test fails and the eleven becomes twelve, visibly, rather than the trigger
    # quietly acquiring a value nobody measured anything under.
    assert POLICIES_OF_RECORD.fault == type(POLICIES_OF_RECORD.fault)()
    assert POLICIES_OF_RECORD.fusion == type(POLICIES_OF_RECORD.fusion)()
    assert POLICIES_OF_RECORD.ladder == type(POLICIES_OF_RECORD.ladder)()
    assert POLICIES_OF_RECORD.cluster == type(POLICIES_OF_RECORD.cluster)()

    assert POLICIES_OF_RECORD.rf is RF_POLICY
    assert POLICIES_OF_RECORD.gap is GAP_POLICY


def test_the_record_satisfies_the_exports_floor_as_the_object_that_ships() -> None:
    # spec: anom-016, eval-003 -- the chain suite already proves a *constructed*
    # policy set records everything the export requires. This proves it of the
    # one object the trigger will actually use, which is the object a figure on
    # screen would be taken under.
    recorded = POLICIES_OF_RECORD.record(_normality_stub(), layout=LAYOUT)

    assert set(REQUIRED_POLICIES) <= set(recorded)


#: The policy types whose construction outside the settings module would be a
#: second declaration of the record. Named rather than discovered, because the
#: guard has to fail when a type is *added* to the record and not quietly pass.
POLICY_TYPES = frozenset(
    {
        "ThresholdPolicy",
        "GapPolicy",
        "BoundingBox",
        "FaultPolicy",
        "FusionPolicy",
        "PrecedencePolicy",
        "ClusterPolicy",
        "DetectorPolicies",
    }
)


def _constructed_policies(path: Path) -> set[str]:
    """Which policy types this file builds for itself."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in POLICY_TYPES
    }


def _imports_from(path: Path, module: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == module
        for alias in node.names
    }


@pytest.mark.parametrize(
    "relative",
    ["measurements/corpus/detection_metrics.py", "tests/test_anom_chain.py"],
)
def test_the_two_existing_copies_of_the_record_read_it_from_the_application(
    relative: str,
) -> None:
    # spec: anom-016 -- the two places the eleven values live today. The figures
    # of record were measured by the first; the second carries a copy annotated
    # "exactly the policies of record", which is a promise rather than a
    # mechanism. Limitation worth stating: this cannot catch a *third* file
    # declaring its own values, only the regrowth of these two. The pin above is
    # what makes a change to the values themselves audible.
    path = BACKEND / relative

    assert _constructed_policies(path) == set()
    assert "POLICIES_OF_RECORD" in _imports_from(path, "app.detection.settings")


# --------------------------------------------- what normal is measured over


def test_the_baseline_is_measured_on_the_metric_it_will_be_thresholded_against(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- the metric is declared twice in the script this replaces:
    # once when the baseline is built and once on the policy the deviation is
    # read against. Disagree and every threshold is measured in the wrong units
    # with nothing failing, because both halves are individually valid. Derived
    # from the policy here, so the two cannot differ.
    from app.detection import chain as chain_module

    monkeypatch.setattr(
        chain_module, "observations_for_run", lambda *_a, **_k: list(_rf(QUIET))
    )
    policies = DetectorPolicies(
        rf=type(RF_POLICY)(
            metric=RfMetric.SNR_DB,
            direction=Direction.BELOW,
            threshold=6.0,
            medium_at=10.0,
            high_at=15.0,
        ),
        fault=POLICIES_OF_RECORD.fault,
        gap=GAP_POLICY,
        cluster=POLICIES_OF_RECORD.cluster,
        fusion=POLICIES_OF_RECORD.fusion,
        ladder=POLICIES_OF_RECORD.ladder,
    )

    normality = measure_normality(
        object(), quiet_run_ids=(QUIET,), policies=policies, window=BASELINE_WINDOW
    )

    assert normality.table.metric is RfMetric.SNR_DB


def test_the_baseline_carries_the_runs_and_the_window_it_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016, anom-015 -- two baselines under identical thresholds give
    # different findings and are otherwise indistinguishable in the record, so
    # `Normality` carries its own provenance. The trigger must not lose it on
    # the way through.
    from app.detection import chain as chain_module

    monkeypatch.setattr(
        chain_module,
        "observations_for_run",
        lambda _f, run_id, *_a, **_k: list(_rf(run_id)),
    )

    normality = measure_normality(
        object(),
        quiet_run_ids=(QUIET, QUIET + 1),
        policies=POLICIES_OF_RECORD,
        window=BASELINE_WINDOW,
    )

    assert normality.quiet_run_ids == (QUIET, QUIET + 1)
    assert normality.window == BASELINE_WINDOW


def test_a_store_with_no_quiet_runs_is_refused_before_the_database_is_touched() -> None:
    # spec: anom-016 -- a freshly generated store always is one: twenty
    # interference runs into an empty database leaves nothing to measure normal
    # against. The refusal is decidable from the id list alone, so it must not
    # cost a read; and baselining against the staged runs instead would measure
    # the incident as normal and report the arm clean, which is worse than
    # refusing because it looks like a detection result.
    with pytest.raises(ChainError, match="no quiet runs"):
        measure_normality(
            _ExplodingFactory(),
            quiet_run_ids=(),
            policies=POLICIES_OF_RECORD,
            window=BASELINE_WINDOW,
        )


# ---------------------------------------------------------- which runs


def test_only_the_runs_this_batch_completed_are_examined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- never the whole store. 300 runs is about six minutes and
    # it would rewrite every figure-of-record run's findings under whatever
    # settings are current, which is the coupling `eval-001` moved off itself.
    # A run that died has partial observations and a run that never opened has
    # no id at all.
    recorder = _Recorder()
    _wire(monkeypatch, recorder)

    report = score_batch(
        _summary(
            _outcome(0, run_id=STAGED[0], completed=True),
            _outcome(1, run_id=STAGED[1], completed=False),
            _outcome(2, run_id=None, completed=False),
        ),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert recorder.runs == [STAGED[0]]
    assert report.scored == (STAGED[0],)
    assert report.requested == (STAGED[0],)


def test_one_baseline_is_measured_for_the_whole_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- the cost that decides where this stage can live. The
    # baseline is 11.2 s and the pass is 1.22 s a run, so one baseline per batch
    # is ~35 s on twenty runs and one per run would be nearly four minutes. The
    # same object has to reach every run besides: a second baseline mid-batch
    # would make two runs of one batch incomparable.
    recorder = _Recorder()
    wiring = _wire(monkeypatch, recorder)

    score_batch(
        _summary(
            _outcome(0, run_id=STAGED[0], completed=True),
            _outcome(1, run_id=STAGED[1], completed=True),
        ),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert wiring.baselines_measured == 1
    assert recorder.normalities == [wiring.baseline, wiring.baseline]


def test_the_settings_the_trigger_scores_under_are_the_ones_of_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- the whole point of the item. A trigger declaring its own
    # policies would put figures on a screen taken under settings that can
    # differ from every quoted number, with nothing able to notice because each
    # copy is internally consistent.
    recorder = _Recorder()
    _wire(monkeypatch, recorder)

    score_batch(
        _summary(_outcome(0, run_id=STAGED[0], completed=True)),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert recorder.policies == [POLICIES_OF_RECORD]


def test_the_run_the_pass_scores_is_read_from_the_row_and_not_from_the_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016, db-007 -- the batch's `completed` flag is the batch's
    # claim; what decides whether a run may be scored is the completion stamp on
    # the row, which is `db-007`'s own definition and `anom-015`'s refusal. So
    # the trigger reads the row rather than assembling a summary from the
    # outcome it already holds.
    recorder = _Recorder()
    _wire(monkeypatch, recorder)
    seen: list[int] = []
    monkeypatch.setattr(
        batch_module,
        "run_summary",
        lambda _factory, run_id: (seen.append(run_id), _run(run_id))[1],
    )

    score_batch(
        _summary(_outcome(0, run_id=STAGED[0], completed=True)),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert seen == [STAGED[0]]


# ------------------------------------------- a failure that must not spread


def test_a_pass_that_fails_on_one_run_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016, scn-003, eval-001 -- record and skip, which is the posture
    # the generator already takes toward a run that dies inside a batch and the
    # campaign takes toward a bundle that fails at 14 of 20. A pass that aborted
    # the batch's scoring on run two would leave eighteen generated runs
    # reporting as unexamined for a reason that applied to one of them.
    recorder = _Recorder(fails=frozenset({STAGED[1]}))
    _wire(monkeypatch, recorder)

    report = score_batch(
        _summary(
            _outcome(0, run_id=STAGED[0], completed=True),
            _outcome(1, run_id=STAGED[1], completed=True),
            _outcome(2, run_id=STAGED[1] + 1, completed=True),
        ),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert report.scored == (STAGED[0], STAGED[1] + 1)
    assert [run_id for run_id, _ in report.failed] == [STAGED[1]]
    assert "refusing" in dict(report.failed)[STAGED[1]]


def test_a_store_with_no_quiet_runs_refuses_the_pass_and_the_batch_still_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- the hours were generated and stored, which is what was
    # asked for. Nothing is scored, nothing is stamped, and the refusal is
    # reported rather than raised: the runs then report themselves unexamined,
    # which `api-012` serves as a null summary and the screen says in words.
    recorder = _Recorder()
    _wire(monkeypatch, recorder, quiet=())

    report = score_batch(
        _summary(_outcome(0, run_id=STAGED[0], completed=True)),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert recorder.runs == []
    assert report.scored == ()
    assert report.refused is not None
    assert "quiet" in report.refused


def test_nothing_about_scoring_escapes_into_the_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- not only the refusals this item anticipated. Anything
    # raising out of here reaches `launch_batch`, which logs "scenario batch
    # failed" -- a false statement, the batch having generated and stored every
    # hour it was asked for. So the catch is broad on purpose, and the report is
    # how a caller learns what happened.
    recorder = _Recorder()
    _wire(monkeypatch, recorder)

    def _gone(_factory: object) -> tuple[int, ...]:
        raise RuntimeError("the store is gone")

    monkeypatch.setattr(batch_module, "quiet_run_ids", _gone)

    report = score_batch(
        _summary(_outcome(0, run_id=STAGED[0], completed=True)),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert isinstance(report, BatchScoring)
    assert report.scored == ()
    assert "the store is gone" in str(report.refused)


def test_a_run_whose_pass_dies_unexpectedly_is_recorded_and_stepped_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- same argument one level in. A `ChainError` is a refusal
    # the pass decided on; anything else is a defect, and a defect on run two
    # must still leave runs one and three examined.
    recorder = _Recorder()
    _wire(monkeypatch, recorder)

    def _explode(run: ScenarioRunSummary, **kwargs: Any) -> object:
        if run.id == STAGED[1]:
            raise ZeroDivisionError("boom")
        return recorder.assess(run, **kwargs)

    monkeypatch.setattr(batch_module, "assess", _explode)

    report = score_batch(
        _summary(
            _outcome(0, run_id=STAGED[0], completed=True),
            _outcome(1, run_id=STAGED[1], completed=True),
        ),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert report.scored == (STAGED[0],)
    assert "boom" in dict(report.failed)[STAGED[1]]


def test_a_batch_that_completed_nothing_is_not_scored_and_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- a batch every run of which failed has nothing to
    # examine, and measuring an 11 s baseline to score nothing is work for no
    # answer. Distinguished from the refusal: there is no store problem here.
    recorder = _Recorder()
    _wire(monkeypatch, recorder)

    report = score_batch(
        _summary(_outcome(0, run_id=None, completed=False)),
        session_factory=_ExplodingFactory(),
        layout=LAYOUT,
    )

    assert report == BatchScoring(requested=(), scored=(), failed=(), refused=None)


def test_a_run_the_store_does_not_hold_is_recorded_and_not_scored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- the batch names its runs by id and the store is the
    # authority on what exists. A missing row is not a reason to stop: the other
    # runs of the batch are there, and reaching the pass with no summary would
    # mean asking it to score a run nothing recorded.
    recorder = _Recorder()
    _wire(monkeypatch, recorder)
    monkeypatch.setattr(batch_module, "run_summary", lambda _factory, _run_id: None)

    report = score_batch(
        _summary(_outcome(0, run_id=STAGED[0], completed=True)),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert recorder.runs == []
    assert report.scored == ()
    assert "not in the store" in dict(report.failed)[STAGED[0]]


def test_the_report_tells_a_refusal_apart_from_an_examination_that_found_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-016 -- the log line is the only place either outcome is stated,
    # and "refused over twenty runs" and "0 of 20 runs examined" are different
    # events: the first is a store with nothing quiet in it, the second a pass
    # that ran and failed on every run. Collapsed into one sentence, a fresh
    # database reads as a broken detector.
    recorder = _Recorder()
    _wire(monkeypatch, recorder, quiet=())
    refused = score_batch(
        _summary(_outcome(0, run_id=STAGED[0], completed=True)),
        session_factory=object(),
        layout=LAYOUT,
    )

    examined = BatchScoring(
        requested=STAGED, scored=(STAGED[0],), failed=((STAGED[1], "no"),), refused=None
    )

    assert "refused over 1 runs" in refused.describe()
    assert examined.describe() == "1 of 2 runs examined, 1 failed"


# ----------------------------------------------------- the two paths differ


def app_modules(module: str) -> set[str]:
    """Every `app` module reachable from `module` through app source.

    Dotted and not top-level: the question here is whether one package reaches
    another inside `app`, which `test_ai_template.py`'s walker collapses away.
    """
    seen: set[str] = set()
    queue = [module]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = BACKEND / Path(*name.split(".")).with_suffix(".py")
        if not path.is_file():
            path = BACKEND / Path(*name.split(".")) / "__init__.py"
        assert path.is_file(), f"cannot read {name} at {path}"
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                targets = [node.module]
            queue.extend(t for t in targets if t.split(".")[0] == "app")
    return seen


def test_the_import_walker_reaches_the_modules_it_claims_to() -> None:
    # spec: anom-016 -- the guard below is an emptiness check, which passes when
    # it works and passes when the walker returns nothing. Fired at a path that
    # certainly exists: the pass imports the rule it composes first.
    reached = app_modules("app.detection.chain")

    assert "app.detection.rf_noise" in reached
    assert "app.db.repository" in reached


def test_the_corpus_building_command_reaches_no_detector() -> None:
    # spec: anom-016, eval-001 -- `python -m app.pipeline` is what the Compose
    # pipeline service and `make generate` run, and it built the 300 hours
    # behind every figure this project quotes. If it scored them it would stamp
    # them with whatever settings were current, and the same hours could never
    # be re-scored under another threshold. Unscored by construction rather than
    # by a parameter somebody must remember not to pass.
    offenders = sorted(
        m for m in app_modules("app.pipeline") if m.startswith("app.detection")
    )

    assert offenders == []


def test_the_interactive_path_does_reach_the_pass() -> None:
    # spec: anom-016 -- the other direction, and the one that is a capability
    # rather than a guard. Without it the test above is satisfied by a project
    # with no detection at all.
    assert "app.detection.chain" in app_modules("app.scenario.batch")


def _function(module: str, name: str) -> ast.FunctionDef:
    path = BACKEND / Path(*module.split(".")).with_suffix(".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{module} has no {name}")


def _calls(statement: ast.stmt, name: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
        for node in ast.walk(statement)
    )


def test_the_interactive_path_generates_first_and_scores_what_it_generated() -> None:
    # spec: anom-016 -- statement order, read off the source, because the two
    # orderings are not both wrong in a way a behavioural test would catch:
    # scoring before generating examines the *previous* batch's runs, which
    # stamps real runs with a real policy and is wrong only in which runs it
    # names. Also that the summary scored is the one generation returned, rather
    # than a second query for recent runs.
    body = _function("app.scenario.batch", "run_batch_now").body
    generated = [i for i, stmt in enumerate(body) if _calls(stmt, "run_batch")]
    scored = [i for i, stmt in enumerate(body) if _calls(stmt, "score_batch")]

    assert len(generated) == 1 and len(scored) == 1
    assert generated[0] < scored[0]

    assign = body[generated[0]]
    assert isinstance(assign, ast.Assign), "the batch summary is not kept"
    assert isinstance(assign.targets[0], ast.Name)
    call = next(
        node
        for node in ast.walk(body[scored[0]])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "score_batch"
    )
    assert isinstance(call.args[0], ast.Name)
    assert call.args[0].id == assign.targets[0].id


def test_the_request_never_scores_anything_itself() -> None:
    # spec: anom-016, api-006, api-011 -- scoring sits inside `run_batch_now`,
    # which `launch_batch` runs on its thread and whose `finally` releases the
    # lease. So the pass holds `api-011`'s guard for its whole duration, which
    # matters because the pass opens its own sessions against the one Engine --
    # the pool exhaustion that guard was written for, measured over generation
    # only. Called from the handler instead, it would both block the request for
    # 35 s and run outside that ordering.
    source = (BACKEND / "app/api/v1/scenario.py").read_text(encoding="utf-8")

    assert "score_batch" not in source


# --------------------------------------- the label the rules may never see


def _identifiers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            out.add(node.arg)
    return out


def _code_strings(path: Path) -> set[str]:
    """Every string constant that is not a docstring.

    Prose is excluded on purpose: three of these modules discuss the quiet runs
    a figure was measured over, which is a sentence about an experiment and not
    a rule reading a label.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


#: The pass and the eight rules. **`control.py` and `sensitivity.py` are
#: excluded, by name and with the reason**: both are instruments that grade a
#: run against ground truth rather than detectors reasoning from observations.
#: `anom-008` reads the label precisely in order to *refuse* anything that is
#: not a quiet run, and `anom-011` records the scenario type among the
#: conditions a recall figure was taken under. An exclusion by directory would
#: have hidden a real one; these two are arguable one at a time.
LABEL_BLIND = (
    "chain",
    "baseline",
    "bundle",
    "clustering",
    "findings",
    "fusion",
    "latency",
    "precedence",
    "rate_excess",
    "rf_noise",
    "sensor_fault",
    "track_gap",
)


@pytest.mark.parametrize("module", LABEL_BLIND)
def test_no_rule_and_not_the_pass_may_see_what_was_injected(module: str) -> None:
    # spec: anom-016, api-009 -- the pass is handed a run summary that carries
    # the scenario type, and must not look at it: the type is the *label* for
    # what was staged, and it discloses the mechanism, the band and that
    # anything was injected at all. `api-012` found that live on the screen's
    # own heading. Written down here because until now it has been a thing done
    # correctly rather than a thing asserted.
    path = BACKEND / "app/detection" / f"{module}.py"

    assert "scenario_type" not in _identifiers(path)
    assert "normal-baseline" not in _code_strings(path)


def test_the_label_check_fires_at_the_module_that_does_read_the_label() -> None:
    # spec: anom-016 -- an interlock. The guard above is two absence checks, and
    # both pass against a checker that reads nothing. `anom-008`'s control
    # genuinely names the quiet type and genuinely takes a scenario type, which
    # is why it is excluded above rather than fixed, so it is the right hazard
    # to fire this at.
    path = BACKEND / "app/detection/control.py"

    assert "scenario_type" in _identifiers(path)
    assert "normal-baseline" in _code_strings(path)


# ------------------------------------------------------ against a database


@requires_database
def test_the_quiet_runs_are_the_completed_baseline_runs_in_id_order(
    factory: sessionmaker,
) -> None:
    # spec: anom-016, anom-002 -- selecting them is the harness's decision and
    # reads the answer key's label; what crosses into the detection layer is
    # ids. Ordered, because a baseline seeded consistently over a population in
    # heap order is reproducible only by accident -- `eval-004`'s own argument
    # for sorting before drawing.
    _open_run(factory, QUIET + 1, scenario_type="normal-baseline")
    _open_run(factory, QUIET, scenario_type="normal-baseline")
    _open_run(factory, STAGED[0], scenario_type="gnss-degradation")

    assert quiet_run_ids(factory) == (QUIET, QUIET + 1)


@requires_database
def test_a_quiet_run_that_is_not_known_to_have_finished_is_not_baselined_over(
    factory: sessionmaker,
) -> None:
    # spec: anom-016, db-007 -- a run that died holds part of an hour, and
    # normality measured partly over a fragment is a number that changes when
    # the run is regenerated. `db-007` records the absence of a completion stamp
    # as exactly that, and `anom-015` already refuses to *score* such a run; the
    # baseline is the other side of the same rule.
    _open_run(factory, QUIET, scenario_type="normal-baseline")
    _open_run(factory, QUIET + 1, scenario_type="normal-baseline", finished=False)

    assert quiet_run_ids(factory) == (QUIET,)


@requires_database
def test_a_store_with_no_quiet_runs_reports_none_rather_than_raising(
    factory: sessionmaker,
) -> None:
    # spec: anom-016 -- one condition, one refusal. The baseline is what refuses
    # a store with no quiet runs, and a second refusal here would mean a caller
    # cannot tell which fired. This reports the store as it is.
    _open_run(factory, STAGED[0], scenario_type="gnss-degradation")

    assert quiet_run_ids(factory) == ()


@requires_database
def test_the_run_summary_is_read_as_the_row_holds_it(factory: sessionmaker) -> None:
    # spec: anom-016 -- including the completion stamp, which is what decides
    # whether the pass will accept the run. An unknown id is None rather than a
    # refusal: the trigger is given ids by a batch summary and a missing row is
    # a fact about the store, reported like any other.
    _open_run(factory, STAGED[0], finished=True)

    found = run_summary(factory, STAGED[0])

    assert found is not None
    assert found.id == STAGED[0]
    assert found.scenario_type == "gnss-degradation"
    assert found.completed_at is not None
    assert run_summary(factory, 999_999) is None


@requires_database
def test_the_baseline_is_the_same_one_the_measurement_script_built_by_hand(
    factory: sessionmaker,
) -> None:
    # spec: anom-016 -- the figures of record were measured with the baseline
    # built inline in `detection_metrics.py`, so moving that build into the
    # application has to produce the same table or every figure quoted from that
    # log describes a baseline nothing can now reproduce. Proved at unit scale
    # here; the full re-run over the corpus is the validation `anom-015` did.
    _store(factory, QUIET, scenario_type="normal-baseline")

    by_hand = compute_rf_baselines(
        [o for run_id in (QUIET,) for o in _rf(run_id)],
        RfMetric.POWER_DBM,
        baseline_run_ids=(QUIET,),
        window=BASELINE_WINDOW,
    )
    through_the_app = measure_normality(
        factory,
        quiet_run_ids=(QUIET,),
        policies=POLICIES_OF_RECORD,
        window=BASELINE_WINDOW,
    )

    assert through_the_app.table.baselines == by_hand.baselines
    assert through_the_app.table.insufficient == by_hand.insufficient


@requires_database
def test_every_completed_run_of_the_batch_ends_up_stamped(
    factory: sessionmaker,
) -> None:
    # spec: anom-016, api-012 -- the whole item, end to end. Before this nothing
    # called the pass outside a measurement script, so every run in the store
    # reported itself unexamined and nothing on the screen changed when a batch
    # finished. The stamp is the only thing that separates a run examined and
    # found clean from a run nobody examined.
    _store(factory, QUIET, scenario_type="normal-baseline")
    for run_id in STAGED:
        _store(factory, run_id)

    report = score_batch(
        _summary(
            _outcome(0, run_id=STAGED[0], completed=True),
            _outcome(1, run_id=STAGED[1], completed=True),
        ),
        session_factory=factory,
        layout=LAYOUT,
    )

    assert report.refused is None
    assert report.scored == STAGED
    assert report.failed == ()
    for run_id in STAGED:
        stamp = detection_pass_for_run(factory, run_id)
        assert stamp is not None
        assert set(REQUIRED_POLICIES) <= set(stamp.policy)
        assert stamp.policy["RF-NOISE.threshold_db"] == "6.0"
        assert stamp.policy["BASELINE.quiet_runs"] == str(QUIET)


@requires_database
def test_a_batch_scored_against_an_empty_store_leaves_every_run_unexamined(
    factory: sessionmaker,
) -> None:
    # spec: anom-016 -- the fresh-database case, end to end: generate a batch of
    # staged runs into a store with no quiet runs and there is nothing to
    # measure normal against. Both runs stay unstamped, which is what `api-012`
    # serves as a null detection summary and the screen states in words. The
    # alternative -- baselining against the staged runs -- would report every
    # one of them clean.
    for run_id in STAGED:
        _store(factory, run_id)

    report = score_batch(
        _summary(
            _outcome(0, run_id=STAGED[0], completed=True),
            _outcome(1, run_id=STAGED[1], completed=True),
        ),
        session_factory=factory,
        layout=LAYOUT,
    )

    assert report.scored == ()
    assert report.refused is not None
    for run_id in STAGED:
        assert detection_pass_for_run(factory, run_id) is None
