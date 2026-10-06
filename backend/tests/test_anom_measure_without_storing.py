"""A measurement writes nothing. Spec: anom-017 (11).

`detection_metrics.py` runs the detection pass to score three hundred hours, and
the pass writes as it goes: findings since `anom-015`, a stamp on every run it
touches, and since `evb-003` the evidence bundles. So the results table could not
be re-measured -- it stopped at the first run the scored campaign cites, on
`db-011`'s refusal -- and every run of it had been re-dating the store.

`assess_without_storing` runs the shipped pass with every write inside one
transaction that is always rolled back. The rules that read stored track findings
back still see them; the store afterwards is exactly as it was. Inside that
transaction, and nowhere else, the bundle write is skipped, which is what lets a
cited run be measured: the guard stops a replacement, and a rolled-back
transaction replaces nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.db.bundles import stored_bundles_for_run
from app.detection import chain as chain_module
from app.detection.chain import assess, assess_without_storing
from tests.conftest import requires_database
from tests.test_anom_chain import LAYOUT, POLICIES, _normality, _run, _store
from tests.test_evb_persisted import LOUD, RUN_ID

BACKEND = Path(__file__).resolve().parents[1]


def _measure(engine: Engine) -> Any:
    return assess_without_storing(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        engine=engine,
    )


def _store_and_score(factory: sessionmaker) -> Any:
    return assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )


def _snapshot(engine: Engine) -> tuple[Any, ...]:
    """Everything a pass over `RUN_ID` could change, read back exactly."""
    with engine.connect() as connection:
        findings = connection.execute(
            text(
                "SELECT id, rule_id, finding_type, subject, started_at, ended_at "
                "FROM detection_findings WHERE scenario_run_id = :run ORDER BY id"
            ),
            {"run": RUN_ID},
        ).all()
        bundles = connection.execute(
            text(
                "SELECT id, anomaly_type, started_at, ended_at FROM evidence_bundles "
                "WHERE scenario_run_id = :run ORDER BY id"
            ),
            {"run": RUN_ID},
        ).all()
        stamp = connection.execute(
            text(
                "SELECT detection_pass_at, detection_policy FROM scenario_runs "
                "WHERE id = :run"
            ),
            {"run": RUN_ID},
        ).one()
        hypotheses = connection.execute(
            text("SELECT count(*) FROM hypotheses")
        ).scalar_one()
    return tuple(findings), tuple(bundles), tuple(stamp), hypotheses


# ------------------------------------------------------ against a database


@requires_database
def test_a_measured_pass_reports_what_the_storing_pass_reports(
    migrated_database: Engine,
) -> None:
    # spec: anom-017 (11) -- it is the shipped pass and not a second
    # composition of the rules, so the two must agree claim for claim -- and
    # measuring first must leave nothing for the storing pass to find.
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)
    before = _snapshot(migrated_database)

    measured = _measure(migrated_database)
    assert _snapshot(migrated_database) == before
    stored = _store_and_score(factory)

    assert measured.reported
    assert measured.reported == stored.reported
    assert len(measured.bundles) == len(stored.bundles)


@requires_database
def test_a_measured_pass_over_an_unexamined_run_leaves_it_unexamined(
    migrated_database: Engine,
) -> None:
    # spec: anom-017 (11) failure case -- "a measurement that changes the store".
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)
    before = _snapshot(migrated_database)

    _measure(migrated_database)

    assert _snapshot(migrated_database) == before
    assert before[0] == () and before[2][0] is None  # the premise: untouched


@requires_database
def test_a_measured_pass_over_a_scored_run_moves_nothing_not_even_the_stamp(
    migrated_database: Engine,
) -> None:
    # spec: anom-017 (11) -- the results table used to re-date every run it
    # scored. Findings replaced with identical rows would still get new ids, so
    # the ids are part of what is compared.
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)
    _store_and_score(factory)
    before = _snapshot(migrated_database)

    _measure(migrated_database)

    assert _snapshot(migrated_database) == before
    assert before[0] and before[1] and before[2][0] is not None


@requires_database
def test_a_cited_run_can_be_measured_and_keeps_its_hypothesis(
    migrated_database: Engine,
) -> None:
    # spec: anom-017 (11) failure case -- "a cited run the measurement cannot
    # score". The storing pass refuses this run (`db-011`); the measurement
    # scores it and the citation survives.
    from app.db.hypotheses import save_hypothesis
    from tests.test_db_hypotheses import template_result

    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)
    _store_and_score(factory)
    bundle_id = stored_bundles_for_run(factory, RUN_ID)[0][0]
    save_hypothesis(
        factory,
        bundle_id=bundle_id,
        result=template_result(),
        requested_generator=template_result().generator,
    )
    before = _snapshot(migrated_database)

    measured = _measure(migrated_database)

    assert measured.reported
    assert _snapshot(migrated_database) == before
    assert before[3] == 1


@requires_database
def test_a_measured_pass_that_fails_part_way_leaves_nothing_behind(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: anom-017 (11) failure case -- "a failure part-way through a measured
    # pass that leaves its earlier writes behind". The track findings are
    # written mid-chain; the stamp is the last write, so failing there means
    # everything before it was written and must be undone.
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)
    before = _snapshot(migrated_database)

    def _fail(*_a: object, **_k: object) -> None:
        raise RuntimeError("the stamp could not be written")

    monkeypatch.setattr(chain_module, "record_detection_pass", _fail)

    with pytest.raises(RuntimeError, match="stamp"):
        _measure(migrated_database)

    assert _snapshot(migrated_database) == before


# --------------------------------------------------------------- structure


def _calls(tree: ast.AST, name: str) -> list[tuple[ast.Call, str | None]]:
    """Every call to `name`, with the function definition it sits in."""
    found: list[tuple[ast.Call, str | None]] = []

    def visit(node: ast.AST, owner: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, ast.FunctionDef) else owner
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == name
            ):
                found.append((child, owner))
            visit(child, inner)

    visit(tree, None)
    return found


def test_only_the_measured_pass_reaches_the_skipped_bundle_write() -> None:
    # spec: anom-017 (11) failure case -- "a way to skip the bundle write that
    # does not roll back". `assess` stores; only `assess_without_storing` may
    # ask the shared body not to.
    path = BACKEND / "app/detection/chain.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    calls = _calls(tree, "_assess")
    assert {owner for _call, owner in calls} == {"assess", "assess_without_storing"}
    for call, owner in calls:
        (flag,) = [k for k in call.keywords if k.arg == "store_bundles"]
        assert isinstance(flag.value, ast.Constant)
        assert flag.value.value is (owner == "assess")


def test_nothing_outside_the_chain_reaches_the_shared_body() -> None:
    # spec: anom-017 (11) -- the private body is the one place the skip lives.
    chain = ast.parse((BACKEND / "app/detection/chain.py").read_text(encoding="utf-8"))
    assert "_assess" in {
        node.name for node in chain.body if isinstance(node, ast.FunctionDef)
    }
    roots = [BACKEND / "app", BACKEND / "measurements"]
    offenders = [
        path.relative_to(BACKEND)
        for root in roots
        for path in root.rglob("*.py")
        if path.name != "chain.py" and "_assess(" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_the_results_table_measures_without_storing() -> None:
    # spec: anom-017 (5), (11) -- the script that produces every quoted
    # detection figure no longer writes to the store it measures.
    path = BACKEND / "measurements/corpus/detection_metrics.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    from_chain = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.detection.chain"
        for alias in node.names
    }
    assert "assess_without_storing" in from_chain
    assert "assess" not in from_chain
