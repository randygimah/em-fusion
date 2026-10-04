"""A bundle a hypothesis cites may not be replaced. Spec: db-011.

**This suite is about a cascade, not about a bundle.** `evb-002` replaces a
run's bundles by deleting them and inserting the new set, which is `db-008`'s
rule for derived data and right for a bundle: it is derived from findings
which are derived from a seed, so appending would leave a superseded bundle
beside a current one with nothing on either to say which is which.

What makes that write dangerous is one column in another table.
`hypotheses.bundle_id` is declared `ON DELETE CASCADE` and is the *only* link
that table has to a run -- there is no `scenario_run_id` on `hypotheses` at
all -- so the delete above takes the hypothesis rows citing it with it. No
error is raised anywhere: the DELETE succeeds, the cascade fires, and the
damage is observable only as rows that are no longer there.

On the store of record, **155 hypothesis rows hang off 20 bundles on runs
102-175** -- `eval-004`'s pre-registered sample, and the one population in
this project that cannot be regenerated, since `db-002` appends rather than
replaces precisely because a model call consumed money and produced one
specific response.

Every test here therefore asserts over **two** tables. A refusal that leaves
the bundle in place while the hypothesis has gone is the failure this item
exists to prevent, and it is invisible to any assertion that looks at the
bundle alone.
"""

from __future__ import annotations

import inspect
from dataclasses import replace

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.db.bundles import (
    CitedBundleError,
    ResolutionError,
    citing_hypotheses,
    save_bundles,
    stored_bundles_for_run,
)
from app.detection.bundle import BundleError
from tests.conftest import RUN_ID, START, requires_database
from tests.test_ai_template import fault_bundle, zone_bundle
from tests.test_db_hypotheses import store, store_a_bundle, template_result
from tests.test_evb_traceability import insert_rf

#: A second run, so "this run is protected" can be told from "every run is".
OTHER_RUN_ID = RUN_ID + 7


def hypothesis_rows(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(text("SELECT count(*) FROM hypotheses")).scalar_one()
        )


def bundle_rows(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT count(*) FROM evidence_bundles")
            ).scalar_one()
        )


def here(run_id: int = RUN_ID):
    """A resolvable interference bundle for one run."""
    return replace(zone_bundle(tracks=False), scenario_run_id=run_id)


def fault_here(run_id: int = RUN_ID):
    """A resolvable fault bundle for one run. Cites RF-03 only."""
    return replace(fault_bundle(), scenario_run_id=run_id)

@pytest.fixture
def second_run(migrated_database: Engine) -> int:
    """Another run with its own observations, for the scoping tests."""
    with migrated_database.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at) "
                "VALUES (:id, 'rf-sensor-fault', '{}'::jsonb, 44, now())"
            ),
            {"id": OTHER_RUN_ID},
        )
        connection.commit()
    for sensor in ("RF-03", "RF-04"):
        insert_rf(
            migrated_database, run_id=OTHER_RUN_ID, sensor=sensor, channel=4, at=START
        )
    return OTHER_RUN_ID


# ----------------------------------------------------- the write, unchanged


@pytest.mark.database
@requires_database
def test_a_run_whose_bundles_nothing_cites_is_written_as_before(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The regression guard, and it must keep passing: `evb-002`'s own suite
    and two committed measurements write bundles over and over on runs that
    carry no hypothesis, and a guard that charged them for the protection
    would be a behaviour change dressed as a safety check."""
    # spec: db-011, evb-002, db-008
    store_a_bundle(migrated_database, factory)
    assert bundle_rows(migrated_database) == 1

    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here(), fault_here()])

    assert bundle_rows(migrated_database) == 2



@pytest.mark.database
@requires_database
def test_an_uncited_run_can_still_be_cleared(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """`evb-002`'s replace rule at zero: a run re-detected as quiet clears
    what was there. Unchanged where nothing cites it."""
    # spec: db-011, evb-002, anom-008
    store_a_bundle(migrated_database, factory)

    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[])

    assert bundle_rows(migrated_database) == 0


# --------------------------------------------------------------- the refusal


@pytest.mark.database
@requires_database
def test_replacing_a_cited_bundle_is_refused(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The protection appears **between two writes with no code change**,
    which is the item's third constraint read as a test: the fact lives in
    `hypotheses.bundle_id` and is read from there, so a twenty-first cited
    bundle protects itself without anybody adding it to a list."""
    # spec: db-011, db-002
    store_a_bundle(migrated_database, factory)
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here()])  # fine so far

    stored = stored_bundles_for_run(factory, RUN_ID)[0][0]
    store(factory, bundle_id=stored, result=template_result())

    with pytest.raises(CitedBundleError):
        save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here()])


@pytest.mark.database
@requires_database
def test_the_refused_write_leaves_the_bundle_in_place(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    # spec: db-011, evb-002
    stored = store_a_bundle(migrated_database, factory)
    store(factory, bundle_id=stored, result=template_result())

    with pytest.raises(CitedBundleError):
        save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here()])

    assert [row_id for row_id, _ in stored_bundles_for_run(factory, RUN_ID)] == [stored]


@pytest.mark.database
@requires_database
def test_the_refused_write_leaves_the_hypothesis_rows_in_place(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The assertion the whole item is for. A guard that refuses *after* the
    delete leaves this count at zero while every bundle assertion still
    passes, because the new set was never inserted."""
    # spec: db-011, db-002, eval-004
    stored = store_a_bundle(migrated_database, factory)
    store(factory, bundle_id=stored, result=template_result())
    store(factory, bundle_id=stored, result=template_result())
    assert hypothesis_rows(migrated_database) == 2

    with pytest.raises(CitedBundleError):
        save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here()])

    assert hypothesis_rows(migrated_database) == 2


@pytest.mark.database
@requires_database
def test_clearing_a_cited_run_is_refused_on_the_same_terms(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Writing an empty set is the same act. `evb-002` makes a zero-bundle
    write clear what was there, which on a cited run is the identical
    cascade with nothing inserted afterwards -- so a guard asserted only
    over a non-empty list leaves the worst case unguarded."""
    # spec: db-011, evb-002, anom-008
    stored = store_a_bundle(migrated_database, factory)
    store(factory, bundle_id=stored, result=template_result())

    with pytest.raises(CitedBundleError):
        save_bundles(factory, scenario_run_id=RUN_ID, bundles=[])

    assert hypothesis_rows(migrated_database) == 1
    assert bundle_rows(migrated_database) == 1


@pytest.mark.database
@requires_database
def test_one_cited_bundle_refuses_the_whole_run(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The delete is per run, so the unit of refusal is the run. An
    implementation that wrote the uncited bundles and skipped the cited one
    would delete both and insert one."""
    # spec: db-011, evb-002, db-008
    for sensor in ("RF-03", "RF-04"):
        insert_rf(migrated_database, run_id=RUN_ID, sensor=sensor, channel=4, at=START)
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here(), fault_here()])
    rows = stored_bundles_for_run(factory, RUN_ID)
    assert len(rows) == 2

    store(factory, bundle_id=rows[0][0], result=template_result())

    with pytest.raises(CitedBundleError):
        save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here()])

    assert len(stored_bundles_for_run(factory, RUN_ID)) == 2


@pytest.mark.database
@requires_database
def test_the_refusal_names_the_run_the_bundles_and_how_many_rows_cite_them(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """A reader meeting this has to tell a protected population from a bug,
    and the two look identical until the numbers are printed -- which is
    `conftest`'s own argument for the database guard's named counts."""
    # spec: db-011
    stored = store_a_bundle(migrated_database, factory)
    for _ in range(3):
        store(factory, bundle_id=stored, result=template_result())

    with pytest.raises(CitedBundleError) as refused:
        save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here()])

    message = str(refused.value)
    assert str(RUN_ID) in message
    assert str(stored) in message
    # Three rather than two, and the noun as well as the digit: RUN_ID is
    # 8812, so `"2" in message` would have passed on the run id alone --
    # an assertion that looks like it checks the count and does not.
    assert "3 hypothes" in message


@pytest.mark.database
@requires_database
def test_the_refusal_precedes_resolution(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Ordering, asserted by which error comes back. The bundle offered here
    cites track observations nothing seeded, so `evb-002` would refuse it --
    and `evb-002` resolves every citation with a query before it writes. A
    refusal decidable from the store alone must not pay for that first."""
    # spec: db-011, evb-002
    stored = store_a_bundle(migrated_database, factory)
    store(factory, bundle_id=stored, result=template_result())
    unresolvable = replace(zone_bundle(tracks=True), scenario_run_id=RUN_ID)

    with pytest.raises(CitedBundleError):
        save_bundles(factory, scenario_run_id=RUN_ID, bundles=[unresolvable])


@pytest.mark.database
@requires_database
def test_a_citation_on_another_run_does_not_protect_this_one(
    migrated_database: Engine, factory: sessionmaker, second_run: int
) -> None:
    """Scoping, in the direction that matters. A guard asking "does any
    hypothesis cite any bundle" protects the whole store the moment one
    campaign has run, which is indistinguishable from the feature working
    until somebody regenerates a corpus and nothing is written."""
    # spec: db-011, evb-002
    save_bundles(factory, scenario_run_id=second_run, bundles=[here(second_run)])
    cited = stored_bundles_for_run(factory, second_run)[0][0]
    store(factory, bundle_id=cited, result=template_result())
    for sensor in ("RF-03", "RF-04"):
        insert_rf(migrated_database, run_id=RUN_ID, sensor=sensor, channel=4, at=START)

    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[here()])

    assert len(stored_bundles_for_run(factory, RUN_ID)) == 1
    assert len(stored_bundles_for_run(factory, second_run)) == 1


# ------------------------------------------------- the cascade that is right


@pytest.mark.database
@requires_database
def test_deleting_the_scenario_run_still_cascades(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """The counterpart, and the reason this is a repository refusal rather
    than `ON DELETE RESTRICT`. Deleting an hour **should** take its bundles
    and their hypotheses with it, a hypothesis having no other route back to
    a run -- so a restriction at the foreign key would block a correct
    delete in order to prevent an incorrect one."""
    # spec: db-011, db-001, db-007
    stored = store_a_bundle(migrated_database, factory)
    store(factory, bundle_id=stored, result=template_result())

    with migrated_database.connect() as connection:
        connection.execute(
            text("DELETE FROM scenario_runs WHERE id = :id"), {"id": RUN_ID}
        )
        connection.commit()

    assert bundle_rows(migrated_database) == 0
    assert hypothesis_rows(migrated_database) == 0


# ------------------------------------------------------------- the predicate


@pytest.mark.database
@requires_database
def test_citing_hypotheses_counts_rows_per_bundle(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Counts and not a boolean, because the refusal has to print the number
    and because one bundle legitimately carries several hypotheses -- a
    model arm's answer and the template that replaced it after a grounding
    failure, which is exactly why `db-002` appends."""
    # spec: db-011, db-002
    stored = store_a_bundle(migrated_database, factory)
    store(factory, bundle_id=stored, result=template_result())
    store(factory, bundle_id=stored, result=template_result())

    assert citing_hypotheses(factory, RUN_ID) == {stored: 2}


@pytest.mark.database
@requires_database
def test_citing_hypotheses_omits_a_bundle_nothing_cites(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    """Omitted rather than carried as a zero: the mapping is the set of
    reasons to refuse, and an entry meaning "no reason" is one an
    implementation can read as a reason by testing for presence."""
    # spec: db-011
    store_a_bundle(migrated_database, factory)

    assert citing_hypotheses(factory, RUN_ID) == {}


@pytest.mark.database
@requires_database
def test_citing_hypotheses_is_empty_for_a_run_with_no_bundles(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    # spec: db-011
    assert citing_hypotheses(factory, RUN_ID) == {}


# ------------------------------------------------------------- structurally


def test_the_write_takes_no_override() -> None:
    """No `force`, no `allow`, no list of exempt runs. An override is a
    convention somebody has to know, which is what `api-013` rejected for
    the hour chooser on the grounds that it downgrades a structural
    guarantee to a disciplinary one."""
    # spec: db-011, api-013
    taken = set(inspect.signature(save_bundles).parameters)

    assert taken == {"session_factory", "scenario_run_id", "bundles"}


def test_the_predicate_takes_no_allowlist() -> None:
    """The protected set is not an input. Decided from the store, so a
    population nobody remembered is protected anyway."""
    # spec: db-011
    taken = list(inspect.signature(citing_hypotheses).parameters)

    assert taken == ["session_factory", "run_id"]


def test_the_refusal_is_not_a_resolution_failure() -> None:
    """A `BundleError`, so the family is right, and **not** a
    `ResolutionError`, because `measurements/corpus/bundle_end_to_end.py`
    catches that one to report an unresolvable citation -- and a protected
    population reported as a traceability defect sends the reader to the
    wrong half of the system."""
    # spec: db-011, evb-002
    assert issubclass(CitedBundleError, BundleError)
    assert not issubclass(CitedBundleError, ResolutionError)
