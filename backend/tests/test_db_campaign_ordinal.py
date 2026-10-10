"""Each stored hypothesis's position in its campaign. Spec: db-012.

The Hypotheses screen shows one explanation per conclusion: the one the blind
scoring used, the first generation the hosted arm was asked for. The store
could not say which row that was. The ordinal was written only in the
committed campaign record, and the earliest row by id was the scored one on
none of the twenty bundles, because trial requests made before the campaign
were stored first.

So the position is stored: written by the campaign from now on, and copied
once from the committed record for the rows already there. Three properties
carry the suite. **A missing position is null and never guessed**, so a row
written outside a campaign is not mistaken for a first generation. **The
record is the authority**: the copy refuses any row it disagrees with and
writes nothing at all rather than part. **Nothing is overwritten**: a row
already holding a different position is refused.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.ai.campaign import GenerationRecord
from app.ai.service import GeneratorKind
from app.db.hypotheses import (
    GroundingStatus,
    HypothesisWriteError,
    hypotheses_for_bundle,
)
from app.db.migrations import alembic_config
from tests.conftest import requires_database
from tests.test_ai_campaign import (
    campaign,
    sample,  # noqa: F401 -- a fixture
)
from tests.test_db_hypotheses import (  # noqa: F401 -- a fixture
    bundle_id,
    column_names,
    hosted_result,
    is_nullable,
    store,
    template_result,
)

HOSTED = GeneratorKind.HOSTED
TEMPLATE = GeneratorKind.TEMPLATE
PREVIOUS = "0009_detection_pass_stamp"


def hypotheses_module() -> Any:
    from app.db import hypotheses

    return hypotheses


def record(bundle: int, ordinal: int, arm: GeneratorKind, row: int) -> GenerationRecord:
    return GenerationRecord(
        bundle_id=bundle,
        ordinal=ordinal,
        requested_arm=arm,
        generator=arm,
        hypothesis_id=row,
        grounding=GroundingStatus.NOT_CHECKED,
        refusals=(),
        usage=None,
        seconds=1.0,
    )


def ordinals(engine: Engine) -> dict[int, int | None]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, campaign_ordinal FROM hypotheses ORDER BY id")
        ).all()
    return {row.id: row.campaign_ordinal for row in rows}


def insert_ordinal(engine: Engine, row: int, ordinal: int) -> None:
    with engine.connect() as connection:
        connection.execute(
            text("UPDATE hypotheses SET campaign_ordinal = :o WHERE id = :id"),
            {"o": ordinal, "id": row},
        )
        connection.commit()


def backfill(factory: sessionmaker, generations: list[GenerationRecord]) -> Any:
    return hypotheses_module().record_campaign_ordinals(factory, generations)


# ------------------------------------------------------------------ the column


@pytest.mark.database
@requires_database
def test_the_position_has_a_nullable_column(migrated_database: Engine) -> None:
    # spec: db-012 -- null means not written by a campaign, or not known.
    assert "campaign_ordinal" in column_names(migrated_database)
    assert is_nullable(migrated_database, "campaign_ordinal")


@pytest.mark.database
@requires_database
def test_a_position_below_one_is_refused_by_the_database(
    migrated_database: Engine, factory: sessionmaker, bundle_id: int  # noqa: F811
) -> None:
    # spec: db-012 -- failure case: an ordinal below 1 is refused by the check.
    row = store(factory, bundle_id=bundle_id, result=hosted_result())
    with pytest.raises(IntegrityError):
        insert_ordinal(migrated_database, row, 0)


@pytest.mark.database
@requires_database
def test_one_bundle_arm_and_position_holds_one_row(
    migrated_database: Engine, factory: sessionmaker, bundle_id: int  # noqa: F811
) -> None:
    # spec: db-012 -- failure case: a second row for the same bundle, asked
    # arm and ordinal is refused by the index.
    first = store(factory, bundle_id=bundle_id, result=hosted_result())
    second = store(factory, bundle_id=bundle_id, result=hosted_result())
    insert_ordinal(migrated_database, first, 1)

    with pytest.raises(IntegrityError):
        insert_ordinal(migrated_database, second, 1)


@pytest.mark.database
@requires_database
def test_the_same_position_under_another_arm_or_null_is_allowed(
    migrated_database: Engine, factory: sessionmaker, bundle_id: int  # noqa: F811
) -> None:
    # spec: db-012 -- the index covers rows that hold a position, per arm.
    hosted = store(factory, bundle_id=bundle_id, result=hosted_result())
    template = store(factory, bundle_id=bundle_id, result=template_result())
    store(factory, bundle_id=bundle_id, result=hosted_result())
    store(factory, bundle_id=bundle_id, result=hosted_result())

    insert_ordinal(migrated_database, hosted, 1)
    insert_ordinal(migrated_database, template, 1)

    assert sorted(v for v in ordinals(migrated_database).values() if v) == [1, 1]


@pytest.mark.database
@requires_database
def test_the_revision_is_reversible(migrated_database: Engine) -> None:
    # spec: db-012 -- the target revision is named, not counted.
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url",
        migrated_database.url.render_as_string(hide_password=False),
    )
    assert "campaign_ordinal" in column_names(migrated_database)

    command.downgrade(config, PREVIOUS)
    assert "campaign_ordinal" not in column_names(migrated_database)

    command.upgrade(config, "head")
    assert "campaign_ordinal" in column_names(migrated_database)


# ------------------------------------------------------------------- the write


@pytest.mark.database
@requires_database
def test_a_row_written_with_a_position_reads_back_with_it(
    factory: sessionmaker, bundle_id: int  # noqa: F811
) -> None:
    # spec: db-012 -- save_hypothesis takes an optional campaign_ordinal and
    # StoredHypothesis carries it.
    hypotheses_module().save_hypothesis(
        factory,
        bundle_id=bundle_id,
        result=hosted_result(),
        requested_generator=HOSTED,
        campaign_ordinal=2,
    )
    [stored] = hypotheses_for_bundle(factory, bundle_id)
    assert stored.campaign_ordinal == 2


@pytest.mark.database
@requires_database
def test_a_row_written_without_a_position_is_null_and_never_one(
    factory: sessionmaker, bundle_id: int  # noqa: F811
) -> None:
    # spec: db-012 -- failure case: save_hypothesis without an ordinal stores
    # NULL, never 1.
    store(factory, bundle_id=bundle_id, result=hosted_result())
    [stored] = hypotheses_for_bundle(factory, bundle_id)
    assert stored.campaign_ordinal is None


@pytest.mark.database
@requires_database
def test_the_campaign_stores_every_rows_position_as_its_record_says(
    factory: sessionmaker, sample: list  # noqa: F811
) -> None:
    # spec: db-012 -- ai-012 passes its ordinal for every row it writes, so a
    # future campaign records it at the source.
    result = campaign(sample, generations=3, factory=factory)
    stored = {
        row.id: row.campaign_ordinal
        for bundle, _ in sample
        for row in hypotheses_for_bundle(factory, bundle)
    }
    generations = [g for g in result.generations if g.hypothesis_id is not None]

    assert generations
    for generation in generations:
        assert stored[generation.hypothesis_id] == generation.ordinal


# -------------------------------------------------- the copy from the record


@pytest.fixture
def three_rows(
    migrated_database: Engine, factory: sessionmaker, bundle_id: int  # noqa: F811
) -> dict[str, int]:
    """A trial row, then the campaign's hosted ordinal 1 and template ordinal 1."""
    return {
        "trial": store(factory, bundle_id=bundle_id, result=hosted_result()),
        "hosted": store(factory, bundle_id=bundle_id, result=hosted_result()),
        "template": store(factory, bundle_id=bundle_id, result=template_result()),
        "bundle": bundle_id,
    }


def the_record(rows: dict[str, int]) -> list[GenerationRecord]:
    return [
        record(rows["bundle"], 1, HOSTED, rows["hosted"]),
        record(rows["bundle"], 1, TEMPLATE, rows["template"]),
    ]


@pytest.mark.database
@requires_database
def test_the_copy_writes_each_recorded_rows_position(
    migrated_database: Engine, factory: sessionmaker, three_rows: dict[str, int]
) -> None:
    # spec: db-012 -- the record is the authority; the copy writes what it says.
    outcome = backfill(factory, the_record(three_rows))

    stored = ordinals(migrated_database)
    assert stored[three_rows["hosted"]] == 1
    assert stored[three_rows["template"]] == 1
    assert outcome.written == 2
    assert outcome.unchanged == 0


@pytest.mark.database
@requires_database
def test_a_row_the_record_does_not_name_stays_null(
    migrated_database: Engine, factory: sessionmaker, three_rows: dict[str, int]
) -> None:
    # spec: db-012 -- never inferred from row order: the trial row came first
    # and keeps no position.
    backfill(factory, the_record(three_rows))
    assert ordinals(migrated_database)[three_rows["trial"]] is None


@pytest.mark.database
@requires_database
def test_running_the_copy_twice_changes_nothing(
    migrated_database: Engine, factory: sessionmaker, three_rows: dict[str, int]
) -> None:
    # spec: db-012 -- running it twice changes nothing, and says so.
    backfill(factory, the_record(three_rows))
    before = ordinals(migrated_database)

    outcome = backfill(factory, the_record(three_rows))

    assert ordinals(migrated_database) == before
    assert (outcome.written, outcome.unchanged) == (0, 2)


@pytest.mark.database
@requires_database
def test_a_recorded_row_missing_from_the_store_is_refused_and_nothing_written(
    migrated_database: Engine, factory: sessionmaker, three_rows: dict[str, int]
) -> None:
    # spec: db-012 -- failure case, and one transaction: the good row before
    # the bad one is not written either.
    generations = the_record(three_rows) + [
        record(three_rows["bundle"], 2, HOSTED, 99999)
    ]

    with pytest.raises(HypothesisWriteError, match="99999"):
        backfill(factory, generations)
    assert all(v is None for v in ordinals(migrated_database).values())


@pytest.mark.database
@requires_database
def test_a_recorded_row_under_another_bundle_is_refused(
    migrated_database: Engine, factory: sessionmaker, three_rows: dict[str, int]
) -> None:
    # spec: db-012 -- failure case: the record's bundle disagrees with the row.
    wrong = [record(three_rows["bundle"] + 1, 1, HOSTED, three_rows["hosted"])]

    with pytest.raises(HypothesisWriteError, match="bundle"):
        backfill(factory, wrong)
    assert all(v is None for v in ordinals(migrated_database).values())


@pytest.mark.database
@requires_database
def test_a_recorded_row_asked_of_another_arm_is_refused(
    migrated_database: Engine, factory: sessionmaker, three_rows: dict[str, int]
) -> None:
    # spec: db-012 -- failure case: the record's asked arm disagrees with the row.
    wrong = [record(three_rows["bundle"], 1, TEMPLATE, three_rows["hosted"])]

    with pytest.raises(HypothesisWriteError, match="arm"):
        backfill(factory, wrong)
    assert all(v is None for v in ordinals(migrated_database).values())


@pytest.mark.database
@requires_database
def test_a_row_already_holding_another_position_is_refused_not_overwritten(
    migrated_database: Engine, factory: sessionmaker, three_rows: dict[str, int]
) -> None:
    # spec: db-012 -- failure case: never overwrite a different ordinal.
    insert_ordinal(migrated_database, three_rows["hosted"], 3)

    with pytest.raises(HypothesisWriteError, match="3"):
        backfill(factory, the_record(three_rows))
    stored = ordinals(migrated_database)
    assert stored[three_rows["hosted"]] == 3
    assert stored[three_rows["template"]] is None
