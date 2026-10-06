"""The pass stores the account it builds. Spec: evb-003.

`anom-015` persists its evidence and, since `api-012`, its conclusions, and
throws away the account that joins them: the bundles are built in the same
function and returned on the `Assessment`, where they are complete inside one
process and do not exist to a web request. `api-015` serves what the store
holds, so until this item every hour the screen offers reports its conclusion
as unexplained -- 140 of the 240 claim-bearing hours in the store, and every
recent one.

**The reason the pass stopped short was sound and narrower than the behaviour
it bought.** `eval-004`'s pre-registered sample names its twenty bundles by
id, so a pass rebuilding them corpus-wide renumbers that population and stops
the draw reproducing itself -- which protects twenty bundles on twenty runs
and was implemented as *store none, ever*. `db-011` makes that protection
structural and decided from the store, after which storing is safe for every
run nothing cites: 380 of 400.

**Order is the half of this that can fail silently.** The bundle write is the
only one of the three that can refuse, so it goes first and a protected run
leaves the store as it was. Written last, a refusal would end the pass with
this hour's conclusions standing beside the previous hour's evidence, and
nothing on either row would say so.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.db.bundles import CitedBundleError, stored_bundles_for_run
from app.detection.chain import assess
from tests.conftest import requires_database
from tests.test_anom_chain import (
    CHANNELS,
    LAYOUT,
    POLICIES,
    SENSORS,
    _normality,
    _run,
    _store,
)

RUN_ID = 2

#: Enough elevation on every channel of one receiver to produce a reported
#: claim, which is what gives the pass a bundle to store at all.
LOUD = {(SENSORS[0], channel): 20.0 for channel in CHANNELS}


def _pass(factory: sessionmaker) -> object:
    return assess(
        _run(),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE scenario_run_id = :run"),
                {"run": RUN_ID},
            ).scalar_one()
        )


def _claims(engine: Engine) -> set[tuple[str, str, str]]:
    with engine.connect() as connection:
        return {
            (row[0], row[1], row[2])
            for row in connection.execute(
                text(
                    "SELECT rule_id, finding_type, subject FROM detection_findings "
                    "WHERE scenario_run_id = :run AND finding_type IN "
                    "('possible_sensor_fault', 'possible_interference_zone')"
                ),
                {"run": RUN_ID},
            )
        }


def _examined(engine: Engine) -> bool:
    with engine.connect() as connection:
        return (
            connection.execute(
                text("SELECT detection_pass_at FROM scenario_runs WHERE id = :run"),
                {"run": RUN_ID},
            ).scalar_one()
            is not None
        )


# ------------------------------------------------------------- what it stores


@requires_database
def test_the_pass_stores_the_bundles_it_builds(migrated_database: Engine) -> None:
    """The item. Before it, `api-015` reports every claim on this run as
    unexplained while the account of it sat on an object nobody kept."""
    # spec: evb-003, anom-015, api-015
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)

    assessment = _pass(factory)

    stored = stored_bundles_for_run(factory, RUN_ID)
    assert len(stored) == len(assessment.bundles) > 0  # type: ignore[attr-defined]


@requires_database
def test_what_is_stored_is_what_the_assessment_reports(
    migrated_database: Engine,
) -> None:
    """Not merely the same count. A pass storing a bundle the assessment does
    not carry would put an account in front of an analyst that nothing in the
    run's own record agrees with."""
    # spec: evb-003, evb-002
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)

    assessment = _pass(factory)

    stored = {
        (b.rule_id, b.subject, b.time_window)
        for _, b in stored_bundles_for_run(factory, RUN_ID)
    }
    built = {(b.rule_id, b.subject, b.time_window) for b in assessment.bundles}  # type: ignore[attr-defined]
    assert stored == built


@requires_database
def test_a_quiet_run_stores_no_bundle(migrated_database: Engine) -> None:
    """`anom-008` requires zero reportable findings of a quiet run and
    `evb-001` refuses an empty bundle, and the way those two agree is that
    nothing is created. `api-015` then serves two empty lists, which is the
    quiet state and distinguishable from the other two."""
    # spec: evb-003, anom-008, evb-001, api-015
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID)

    _pass(factory)

    assert _count(migrated_database, "evidence_bundles") == 0
    assert _examined(migrated_database)


@requires_database
def test_re_running_the_pass_replaces_rather_than_appends(
    migrated_database: Engine,
) -> None:
    """`db-008`'s rule, which the bundle write already follows. Appending
    would leave a superseded account beside a current one with nothing on
    either to say which is which, and `api-015` would refuse the run for an
    ambiguous match key."""
    # spec: evb-003, db-008, evb-002, api-015
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)

    _pass(factory)
    first = _count(migrated_database, "evidence_bundles")
    _pass(factory)

    assert _count(migrated_database, "evidence_bundles") == first > 0


# ------------------------------------------------------- the refusal, and order


@pytest.fixture
def cited(migrated_database: Engine) -> sessionmaker:
    """A run already scored, with a hypothesis citing one of its bundles.

    Built by running the pass rather than by hand, so what is protected is a
    bundle the shipped writer produced.
    """
    from app.db.hypotheses import save_hypothesis
    from tests.test_db_hypotheses import template_result

    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)
    _pass(factory)
    bundle_id = stored_bundles_for_run(factory, RUN_ID)[0][0]
    save_hypothesis(
        factory,
        bundle_id=bundle_id,
        result=template_result(),
        requested_generator=template_result().generator,
    )
    return factory


@requires_database
def test_the_pass_propagates_the_refusal_rather_than_swallowing_it(
    cited: sessionmaker,
) -> None:
    """A run whose account may not be replaced is a run somebody must be told
    about. `scn-003` and `eval-001`'s recorded-and-stepped-over rule applies at
    the batch, which already records a per-run failure and continues."""
    # spec: evb-003, db-011, scn-003, eval-001
    with pytest.raises(CitedBundleError):
        _pass(cited)


@requires_database
def test_a_refused_run_keeps_the_conclusions_it_already_had(
    cited: sessionmaker, migrated_database: Engine
) -> None:
    """**The ordering assertion**, and the reason the bundle write goes first.
    Written last, a refusal would end the pass with this hour's conclusions
    standing beside the previous hour's evidence — a disagreement no property
    of either row can detect."""
    # spec: evb-003, db-011, db-008
    before = _claims(migrated_database)
    assert before  # the premise: there is something to lose

    with pytest.raises(CitedBundleError):
        _pass(cited)

    assert _claims(migrated_database) == before


@requires_database
def test_a_refused_run_keeps_its_bundles_and_its_hypothesis(
    cited: sessionmaker, migrated_database: Engine
) -> None:
    """The thing `db-011` exists for, asserted through the pass rather than
    through the repository: 155 rows on the store of record hang off twenty
    bundles by a cascading delete."""
    # spec: evb-003, db-011, db-002
    bundles = _count(migrated_database, "evidence_bundles")

    with pytest.raises(CitedBundleError):
        _pass(cited)

    with migrated_database.connect() as connection:
        rows = int(
            connection.execute(text("SELECT count(*) FROM hypotheses")).scalar_one()
        )
    assert _count(migrated_database, "evidence_bundles") == bundles > 0
    assert rows == 1


@requires_database
def test_a_run_refused_before_it_was_ever_examined_stays_unexamined(
    migrated_database: Engine,
) -> None:
    """The stamp is written last, after every write the pass makes, so it
    means the pass finished everything it writes. A refusal must not leave a
    complete-looking record over a store that was never touched."""
    # spec: evb-003, anom-015, db-011
    from app.db.bundles import save_bundles
    from app.db.hypotheses import save_hypothesis
    from tests.test_db_hypotheses import template_result

    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, RUN_ID, elevate=LOUD)
    # A bundle and a citation planted WITHOUT running the pass, so the run has
    # never been stamped.
    assessment = assess(
        _run(run_id=RUN_ID),
        normality=_normality(),
        policies=POLICIES,
        layout=LAYOUT,
        session_factory=factory,
    )
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=assessment.bundles)
    save_hypothesis(
        factory,
        bundle_id=stored_bundles_for_run(factory, RUN_ID)[0][0],
        result=template_result(),
        requested_generator=template_result().generator,
    )
    with migrated_database.connect() as connection:
        connection.execute(
            text("UPDATE scenario_runs SET detection_pass_at = NULL WHERE id = :run"),
            {"run": RUN_ID},
        )
        connection.commit()

    with pytest.raises(CitedBundleError):
        _pass(factory)

    assert not _examined(migrated_database)


# --------------------------------------------------------- the identity itself


def test_the_identity_is_derived_in_one_place() -> None:
    """`api-015`'s match key and `evb-003`'s comparison are the same question,
    so they are the same function. Asserted structurally: the schemas module
    imports the derivation rather than spelling it."""
    # spec: evb-003, api-015
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app/api/v1/schemas/evidence.py"
    ).read_text()
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module == "app.detection.findings"
        for alias in node.names
    }

    assert "claim_identity" in imported


def test_the_identity_of_two_findings_of_one_claim_is_equal() -> None:
    # spec: evb-003, api-015
    from dataclasses import replace

    from app.detection.findings import claim_identity
    from tests.test_api_evidence import claim_for, fault

    one = claim_for(fault())
    again = replace(one, details={"anything": "else"})

    assert claim_identity(one) == claim_identity(again)


def test_a_different_window_is_a_different_claim() -> None:
    """The four stale bundles on the store of record differ from their claim
    by one or two sampling intervals at one end of the window, and that is
    exactly the disagreement the fill has to notice."""
    # spec: evb-003, api-015
    from dataclasses import replace
    from datetime import timedelta

    from app.detection.findings import claim_identity
    from tests.test_api_evidence import claim_for, fault

    one = claim_for(fault())
    moved = replace(one, ended_at=one.ended_at + timedelta(seconds=10))

    assert claim_identity(one) != claim_identity(moved)


def test_the_identity_carries_no_detail_and_no_location() -> None:
    """Details are rule-internal and a location is derived from them, so a
    claim whose confidence changed under new settings would read as a
    different claim and the fill would refuse a run for the wrong reason."""
    # spec: evb-003
    from app.detection.findings import claim_identity
    from tests.test_api_evidence import claim_for, fault

    identity = claim_identity(claim_for(fault()))

    assert len(identity) == 5
    assert all(not isinstance(part, dict) for part in identity)
