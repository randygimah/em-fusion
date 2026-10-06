"""The baseline population is declared, not discovered. Spec: anom-017.

`measure_normality` was handed every quiet run the store held, so the normality a
run was scored against depended on how large the store was when the pass ran. The
store of record ended up holding findings under two baselines -- 378 runs at sixty
quiet runs and 80 at a hundred -- and the same hour under the same thresholds put
one claim's window twenty seconds apart. Nothing failed; the two were
indistinguishable except by the stamp `anom-016` had put on the run.

Three groups. **The constant**: a hundred runs, each with its seed, pinned by value
and held to be a literal rather than a query. **The refusal**: a pinned run the
store does not hold *as pinned* -- absent, unfinished, not quiet, or carrying a
different seed -- refuses the baseline before a single observation is read, naming
every run that failed. **The callers**: the batch trigger measures normal over the
constant and no longer asks the store which runs are quiet, and the two
measurement scripts that build a baseline read the same constant.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.repository import pinned_run_discrepancies
from app.detection import chain as chain_module
from app.detection.chain import ChainError, PinnedRun, measure_normality
from app.detection.settings import (
    BASELINE_QUIET_RUNS,
    BASELINE_WINDOW,
    POLICIES_OF_RECORD,
)
from app.pipeline import BatchSummary, RunOutcome
from app.scenario import batch as batch_module
from app.scenario.batch import score_batch
from app.scenario.layout import load_layout
from tests.conftest import requires_database

BACKEND = Path(__file__).resolve().parents[1]
LAYOUT = load_layout()

#: The five batches the hundred quiet runs came from, twenty each. The middle
#: three are the corpus of record's own base seeds; 21-40 and 381-400 are the two
#: further batches the 60-run baseline did not include.
POPULATION = (
    tuple(range(21, 41))
    + tuple(range(81, 101))
    + tuple(range(181, 201))
    + tuple(range(281, 301))
    + tuple(range(381, 401))
)

#: SHA-256 over `"<id>:<seed>\n"` for every pinned run in id order, taken from
#: the store of record on 2026-10-06. A digest rather than a second spelling of
#: a hundred seeds: a pin is an assertion about the values, and a hundred-line
#: copy is a second place for them to be edited.
PINNED_DIGEST = "efabc8f7fcaf8b9f03334f118139e99269d7605e9881e11f397ea2364b428f49"


class _ExplodingFactory:
    """A session factory whose use is a test failure."""

    def __call__(self) -> Any:  # pragma: no cover -- calling it is the failure
        raise AssertionError("the baseline reached the database before refusing")

    def begin(self) -> Any:  # pragma: no cover -- same
        raise AssertionError("the baseline reached the database before refusing")


def _no_observations(*_a: object, **_k: object) -> list[object]:
    raise AssertionError("an observation was read before the refusal")


# ------------------------------------------------------------- the constant


def test_the_population_is_the_hundred_quiet_runs_of_corpus_v2() -> None:
    # spec: anom-017 (1) -- all hundred, because the sixty are a strict subset of
    # them and every one of the hundred is corpus v2: one population measured
    # twice, not two to choose between.
    assert tuple(run.run_id for run in BASELINE_QUIET_RUNS) == POPULATION


def test_the_sixty_the_figures_were_first_measured_over_are_a_subset() -> None:
    # spec: anom-017 (1) -- the measured fact the choice rests on, kept beside it
    # so a later edit to the constant that dropped one of them is audible.
    sixty = set(range(81, 101)) | set(range(181, 201)) | set(range(281, 301))

    assert sixty < {run.run_id for run in BASELINE_QUIET_RUNS}


def test_every_pinned_run_carries_the_seed_the_store_of_record_holds() -> None:
    # spec: anom-017 (8) -- an id names a row in one store; the seed names its
    # content. Pinned by digest, so a changed seed or a reordering both fail.
    canonical = "".join(f"{run.run_id}:{run.seed}\n" for run in BASELINE_QUIET_RUNS)

    assert hashlib.sha256(canonical.encode()).hexdigest() == PINNED_DIGEST


def test_the_constant_is_in_id_order_with_no_repeats() -> None:
    # spec: anom-017 -- a baseline over a population in heap order is
    # reproducible only by accident, and a repeated run is counted twice.
    ids = [run.run_id for run in BASELINE_QUIET_RUNS]

    assert len(ids) == 100
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_the_constant_is_a_literal_and_not_a_query_against_the_store() -> None:
    # spec: anom-017 (2) -- the failure case "a constant that is still a query
    # against the store, which is the defect wearing a name". The settings
    # module reaches no database and builds the constant from literals only.
    path = BACKEND / "app/detection/settings.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(m.startswith(("app.db", "sqlalchemy")) for m in imported)

    (assigned,) = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign | ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "BASELINE_QUIET_RUNS"
            for target in (
                [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            )
        )
    ]
    calls = {
        node.func.id
        for node in ast.walk(assigned)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls == {"PinnedRun"}


# -------------------------------------------------------------- the refusal


def test_an_empty_population_is_still_refused_before_the_database() -> None:
    # spec: anom-017, anom-016 -- the existing refusal survives the change of
    # argument: nothing pinned is nothing to measure over.
    with pytest.raises(ChainError, match="no quiet runs"):
        measure_normality(
            _ExplodingFactory(),
            quiet_runs=(),
            policies=POLICIES_OF_RECORD,
            window=BASELINE_WINDOW,
        )


def test_a_run_pinned_twice_is_refused_before_the_database() -> None:
    # spec: anom-017 -- a repeated run would be read twice and weighted double,
    # which is a different baseline under the same name.
    with pytest.raises(ChainError, match="21"):
        measure_normality(
            _ExplodingFactory(),
            quiet_runs=(PinnedRun(21, 5), PinnedRun(21, 5)),
            policies=POLICIES_OF_RECORD,
            window=BASELINE_WINDOW,
        )


def test_a_pinned_run_the_store_does_not_hold_is_refused_before_any_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-017 (3) -- a baseline over 99 of its 100 runs is a different
    # baseline, so a missing run refuses rather than quietly narrowing it, and
    # it refuses before an observation is read.
    monkeypatch.setattr(
        chain_module,
        "pinned_run_discrepancies",
        lambda _factory, pinned: ((22, "absent"),),
    )
    monkeypatch.setattr(chain_module, "observations_for_run", _no_observations)

    with pytest.raises(ChainError, match=r"22.*absent"):
        measure_normality(
            object(),
            quiet_runs=(PinnedRun(21, 5), PinnedRun(22, 6)),
            policies=POLICIES_OF_RECORD,
            window=BASELINE_WINDOW,
        )


def test_every_failing_run_is_named_and_not_only_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-017 (8) -- "naming every run that failed and why". A refusal
    # naming the first would be repaired one run at a time.
    monkeypatch.setattr(
        chain_module,
        "pinned_run_discrepancies",
        lambda _factory, pinned: ((21, "absent"), (22, "seed 9, pinned 6")),
    )
    monkeypatch.setattr(chain_module, "observations_for_run", _no_observations)

    with pytest.raises(ChainError) as refused:
        measure_normality(
            object(),
            quiet_runs=(PinnedRun(21, 5), PinnedRun(22, 6)),
            policies=POLICIES_OF_RECORD,
            window=BASELINE_WINDOW,
        )

    assert "21" in str(refused.value)
    assert "absent" in str(refused.value)
    assert "22" in str(refused.value)
    assert "seed 9, pinned 6" in str(refused.value)


def test_the_check_is_asked_about_exactly_the_pinned_runs_and_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-017 (8) -- the seed has to reach the check, or an id that
    # exists as a different run passes it.
    asked: list[tuple[tuple[int, int], ...]] = []

    def _check(_factory: object, pinned: Any) -> tuple[()]:
        asked.append(tuple(pinned))
        return ()

    monkeypatch.setattr(chain_module, "pinned_run_discrepancies", _check)
    monkeypatch.setattr(chain_module, "observations_for_run", lambda *_a, **_k: [])

    with pytest.raises(Exception):  # an empty table is refused downstream
        measure_normality(
            object(),
            quiet_runs=(PinnedRun(21, 5), PinnedRun(22, 6)),
            policies=POLICIES_OF_RECORD,
            window=BASELINE_WINDOW,
        )

    assert asked == [((21, 5), (22, 6))]


def test_the_normality_records_the_pinned_ids_it_was_measured_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-017, anom-015 -- the provenance the stamp carries is unchanged
    # in shape: the ids, which is what `eval-003` exports.
    from tests.test_anom_batch_trigger import _rf

    monkeypatch.setattr(
        chain_module, "pinned_run_discrepancies", lambda _factory, pinned: ()
    )
    monkeypatch.setattr(
        chain_module,
        "observations_for_run",
        lambda _f, run_id, *_a, **_k: list(_rf(run_id)),
    )

    normality = measure_normality(
        object(),
        quiet_runs=(PinnedRun(101, 5), PinnedRun(102, 6)),
        policies=POLICIES_OF_RECORD,
        window=BASELINE_WINDOW,
    )

    assert normality.quiet_run_ids == (101, 102)


# --------------------------------------------------------------- the callers


def _outcome(run_id: int) -> RunOutcome:
    from datetime import UTC, datetime

    return RunOutcome(
        index=0,
        seed=7,
        scenario_type="gnss-degradation",
        start=datetime(2022, 6, 27, 12, tzinfo=UTC),
        duration_seconds=600,
        run_id=run_id,
        completed=True,
    )


def test_the_batch_trigger_measures_normal_over_the_pinned_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # spec: anom-017 (9) -- the trigger is the caller that made the baseline
    # vary: every batch from the screen re-read the store's quiet runs.
    seen: dict[str, Any] = {}

    def _measure(_factory: object, **kwargs: Any) -> object:
        seen.update(kwargs)
        raise ChainError("stop here")

    monkeypatch.setattr(batch_module, "measure_normality", _measure)

    report = score_batch(
        BatchSummary(
            base_seed=1,
            scenario_type="gnss-degradation",
            runs=(_outcome(501),),
            seconds=1.0,
        ),
        session_factory=object(),
        layout=LAYOUT,
    )

    assert seen["quiet_runs"] == BASELINE_QUIET_RUNS
    assert report.refused is not None


def test_the_batch_trigger_no_longer_asks_the_store_which_runs_are_quiet() -> None:
    # spec: anom-017 failure case -- "a batch trigger still reading
    # `quiet_run_ids`". Structural, because a behavioural test that patches
    # `measure_normality` cannot see an unused second source.
    path = BACKEND / "app/scenario/batch.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "quiet_run_ids" not in names
    assert "BASELINE_QUIET_RUNS" in names


@pytest.mark.parametrize(
    "relative",
    ["measurements/corpus/detection_metrics.py", "measurements/corpus/rescore_baseline.py"],
)
def test_the_scripts_that_build_a_baseline_read_the_pinned_constant(
    relative: str,
) -> None:
    # spec: anom-017 (5), (10) -- the results table and the re-score are the two
    # scripts that build a baseline, and a third population declared in either
    # is the drift this item removes.
    path = BACKEND / relative
    tree = ast.parse(path.read_text(encoding="utf-8"))

    from_settings = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.detection.settings"
        for alias in node.names
    }
    assert "BASELINE_QUIET_RUNS" in from_settings
    assert "quiet_runs(" not in path.read_text(encoding="utf-8")
    assert "quiet_run_ids(" not in path.read_text(encoding="utf-8")


def test_the_old_rescore_is_retired_from_the_corpus_scripts() -> None:
    # spec: anom-017 (10) -- it baselines over sixty and rewrites every stamp, so
    # it moves where nothing runs it by accident.
    assert not (BACKEND / "measurements/corpus/rescore_corpus.py").exists()
    assert (BACKEND / "measurements/superseded/rescore_corpus.py").exists()


# ------------------------------------------------------- against a database


def _row(
    factory: sessionmaker,
    run_id: int,
    *,
    seed: int,
    scenario_type: str = "normal-baseline",
    finished: bool = True,
) -> None:
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO scenario_runs (id, scenario_type, parameters, seed, "
                "started_at, completed_at) VALUES (:id, :kind, '{}'::jsonb, :seed, "
                "now(), CASE WHEN :finished THEN now() END)"
            ),
            {"id": run_id, "kind": scenario_type, "seed": seed, "finished": finished},
        )


@requires_database
def test_a_run_held_as_pinned_has_no_discrepancy(factory: sessionmaker) -> None:
    # spec: anom-017 (8) -- asked beside one that is absent, so a check that
    # reports nothing at all cannot pass it.
    _row(factory, 101, seed=5)

    found = pinned_run_discrepancies(factory, ((101, 5), (102, 6)))

    assert [run_id for run_id, _reason in found] == [102]


@requires_database
def test_each_way_a_pinned_run_can_fail_is_named(factory: sessionmaker) -> None:
    # spec: anom-017 (8) -- exists, completed, quiet, and the pinned seed: four
    # conditions, four reasons, in id order.
    _row(factory, 102, seed=6, finished=False)
    _row(factory, 103, seed=7, scenario_type="gnss-degradation")
    _row(factory, 104, seed=99)

    found = dict(
        pinned_run_discrepancies(factory, ((104, 8), (101, 5), (103, 7), (102, 6)))
    )

    assert list(found) == [101, 102, 103, 104]
    assert "absent" in found[101]
    assert "not completed" in found[102]
    assert "not normal-baseline" in found[103]
    assert "seed 99" in found[104] and "pinned 8" in found[104]


@requires_database
def test_a_pinned_id_that_exists_as_a_different_run_is_refused(
    factory: sessionmaker,
) -> None:
    # spec: anom-017 (8) failure case -- "a pinned id that exists in the store as
    # a different run, accepted". The run is quiet and finished; only the seed
    # says it is not the run that was pinned.
    _row(factory, 101, seed=5)

    with pytest.raises(ChainError, match="101"):
        measure_normality(
            factory,
            quiet_runs=(PinnedRun(101, 6),),
            policies=POLICIES_OF_RECORD,
            window=BASELINE_WINDOW,
        )
