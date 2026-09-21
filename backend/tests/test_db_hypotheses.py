"""Storing a hypothesis, and what makes one reproducible. Spec: db-002.

The system can produce an explanation three ways and cannot save one. The
table was created in `0001`, before the explanation had a settled shape,
and comparing it against what the rest of the system has since decided
turns up four problems -- two fields with no column at all, three under
different names, a flag that cannot say "not yet checked", and a review
status accepting any text while the columns either side of it are
constrained.

The urgency is written into `0001` itself: *a column added late, after an
evaluation campaign has run against a hosted model, is a campaign that has
to be repeated.* The table holds zero rows today, so every change here is
free; after the campaign none of them are.

Three properties carry most of this suite.

**Renamed, not mapped.** A translation layer between two vocabularies is a
permanent place for them to drift, and the drift is silent: a hypothesis
stored with one field's content under another field's name complains to
nobody. The table is empty, so the rename is available exactly once.

**`grounding_passed` is three-valued.** A hypothesis is written before
`ai-008` examines it, so a two-valued flag forces a row to claim an outcome
it does not have -- and makes *failed the check* and *was never checked*
identical. That is `evb-001`'s typed-absence principle, and this
repository has now recorded the same collapse three times.

**Writes append; they never replace.** `db-008` replaces findings per run
per rule, and the asymmetry is principled rather than an oversight: a
finding is derived and regenerable from a seed, while a model call
consumed money and produced one specific response. Two calls are two
facts, and `db-007` says nothing is deleted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.ai.hypothesis import Confidence, Hypothesis
from app.ai.service import GenerationResult, GeneratorKind, ModelCall, Usage
from app.ai.template import generate as template_generate
from app.db.bundles import save_bundles, stored_bundles_for_run
from app.db.hypotheses import (
    GroundingStatus,
    HypothesisWriteError,
    ReviewStatus,
    hypotheses_for_bundle,
    save_hypothesis,
)
from app.db.migrations import alembic_config
from tests.conftest import requires_database
from tests.test_ai_template import fault_bundle, zone_bundle
from tests.test_evb_traceability import insert_rf

RUN_ID = 8812
START = datetime(2022, 6, 27, 12, 0, tzinfo=UTC)


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    """Schema at head, holding one scenario run for the bundles to hang off."""
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
                "VALUES (:id, 'gnss-degradation', '{}'::jsonb, 42, now())"
            ),
            {"id": RUN_ID},
        )
        connection.commit()
    return empty_database


@pytest.fixture
def factory(migrated_database: Engine) -> sessionmaker:
    return sessionmaker(bind=migrated_database, autoflush=False)


def store_a_bundle(engine: Engine, factory: sessionmaker) -> int:
    """One real bundle, through the real writer, and its row id.

    The observations are seeded first because `evb-002` resolves every
    citation before it will store anything -- which is the whole point of
    it, and which makes an unseeded database refuse the bundle rather than
    store one nothing can look up. Going round that with a hand-written
    INSERT would make these tests pass against a bundle the shipped writer
    would not accept.
    """
    from dataclasses import replace

    for sensor in ("RF-03", "RF-04"):
        insert_rf(engine, run_id=RUN_ID, sensor=sensor, channel=4, at=START)

    bundle = replace(zone_bundle(tracks=False), scenario_run_id=RUN_ID)
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[bundle])
    return stored_bundles_for_run(factory, RUN_ID)[0][0]


@pytest.fixture
def bundle_id(migrated_database: Engine, factory: sessionmaker) -> int:
    """One stored bundle, and its identity.

    Exposing that identity is itself part of this item: a hypothesis
    references a bundle by id and `evb-002`'s reader returned none, which
    is a blocker found by attempting the write rather than by reading the
    schema.
    """
    return store_a_bundle(migrated_database, factory)


def a_hypothesis() -> Hypothesis:
    return template_generate(fault_bundle())


def a_call(**kw: Any) -> ModelCall:
    kw.setdefault("model_id", "some-model-2026-01-01")
    kw.setdefault("parameters", {"temperature": 0.0, "max_tokens": 2048})
    kw.setdefault("raw_response", '{"hypothesis_title": "Possible sensor fault"}')
    kw.setdefault(
        "usage", Usage(prompt_tokens=1667, completion_tokens=400, cost_usd=0.012)
    )
    return ModelCall(**kw)


def template_result() -> GenerationResult:
    return GenerationResult(
        hypothesis=a_hypothesis(), generator=GeneratorKind.TEMPLATE, call=None
    )


def hosted_result(**kw: Any) -> GenerationResult:
    return GenerationResult(
        hypothesis=kw.pop("hypothesis", a_hypothesis()),
        generator=GeneratorKind.HOSTED,
        call=a_call(**kw),
    )


def column_names(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'hypotheses'"
                )
            )
        }


def is_nullable(engine: Engine, column: str) -> bool:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT is_nullable = 'YES' FROM information_schema.columns "
                "WHERE table_name = 'hypotheses' AND column_name = :c"
            ),
            {"c": column},
        ).scalar_one()


# ------------------------------------------------------------------- the shape


@pytest.mark.database
@requires_database
def test_every_field_of_a_hypothesis_has_a_column(migrated_database: Engine) -> None:
    # spec: db-002, ai-001 -- read off the model rather than listed here, so
    # a field added to the schema later fails this instead of being stored
    # nowhere.
    columns = column_names(migrated_database)

    missing = [name for name in Hypothesis.model_fields if name not in columns]

    assert missing == []


@pytest.mark.database
@requires_database
def test_the_columns_are_renamed_not_duplicated(migrated_database: Engine) -> None:
    # spec: db-002 -- a mapping layer between two vocabularies is a
    # permanent place for them to drift silently, so the old names go.
    columns = column_names(migrated_database)

    assert {"title", "uncertainty", "alternatives"} & columns == set()


@pytest.mark.database
@requires_database
def test_the_two_missing_columns_are_required(migrated_database: Engine) -> None:
    # spec: db-002 -- the summary an analyst reads first and the action that
    # is the point of decision support. Nullable, they could be quietly
    # absent on every row.
    assert not is_nullable(migrated_database, "summary")
    assert not is_nullable(migrated_database, "recommended_human_action")


@pytest.mark.database
@requires_database
def test_the_grounding_flag_can_say_it_has_not_been_checked(
    migrated_database: Engine,
) -> None:
    # spec: db-002, ai-008, evb-001 -- a hypothesis is written before the
    # grounding check runs, so a NOT NULL boolean forces the row to claim
    # an outcome it does not have.
    assert is_nullable(migrated_database, "grounding_passed")


@pytest.mark.database
@requires_database
def test_the_reproducibility_columns_stay_nullable(
    migrated_database: Engine,
) -> None:
    # spec: db-002 -- because the template arm genuinely has no model. The
    # presence rule for the two model arms is enforced at the repository
    # boundary, where the generator is known.
    for column in ("model_id", "generation_params", "raw_response"):
        assert is_nullable(migrated_database, column), column


@pytest.mark.database
@requires_database
def test_an_unknown_review_status_is_refused_by_the_database(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, FR-602 -- five review states are named in the
    # requirements and the column accepted any text at all, while the two
    # columns either side of it both carried check constraints.
    save_hypothesis(factory, bundle_id=bundle_id, result=template_result())

    with pytest.raises(DBAPIError):
        with factory.begin() as session:
            session.execute(text("UPDATE hypotheses SET status = 'Probably fine'"))


@pytest.mark.parametrize("status", [s.value for s in ReviewStatus])
@pytest.mark.database
@requires_database
def test_every_named_review_state_is_accepted(
    factory: sessionmaker, bundle_id: int, status: str
) -> None:
    # spec: db-002, FR-602 -- the other direction. A constraint that also
    # refuses a legitimate value is worse than none, because the first
    # person to hit it widens it to anything.
    save_hypothesis(factory, bundle_id=bundle_id, result=template_result())

    with factory.begin() as session:
        session.execute(text("UPDATE hypotheses SET status = :s"), {"s": status})


# ------------------------------------------------------------------- the write


@pytest.mark.database
@requires_database
def test_a_template_hypothesis_is_stored_with_no_model_behind_it(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-002
    save_hypothesis(factory, bundle_id=bundle_id, result=template_result())

    stored = hypotheses_for_bundle(factory, bundle_id)

    assert len(stored) == 1
    assert stored[0].generator is GeneratorKind.TEMPLATE
    assert stored[0].model_id is None
    assert stored[0].raw_response is None
    assert stored[0].generation_params is None


@pytest.mark.database
@requires_database
def test_a_model_hypothesis_stores_the_model_its_parameters_and_its_response(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, NFR-602, US-R3 -- the four columns that make a result
    # reproducible, populated on write.
    result = hosted_result()

    save_hypothesis(factory, bundle_id=bundle_id, result=result)
    stored = hypotheses_for_bundle(factory, bundle_id)[0]

    assert stored.generator is GeneratorKind.HOSTED
    assert stored.model_id == "some-model-2026-01-01"
    assert stored.generation_params == {"temperature": 0.0, "max_tokens": 2048}
    assert stored.raw_response == result.call.raw_response  # type: ignore[union-attr]


@pytest.mark.database
@requires_database
def test_the_raw_response_is_stored_verbatim_and_not_reserialised(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- the difference only ever shows up once: when somebody
    # investigates a grounding failure months later and finds a record of
    # what was understood rather than of what was said. So the stored text
    # is deliberately NOT valid against the schema it came with.
    ragged = '  {"hypothesis_title": "x", "extra": 1}\n\n trailing prose  '

    save_hypothesis(
        factory, bundle_id=bundle_id, result=hosted_result(raw_response=ragged)
    )

    assert hypotheses_for_bundle(factory, bundle_id)[0].raw_response == ragged


@pytest.mark.database
@requires_database
def test_every_field_of_the_hypothesis_survives_the_round_trip(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-001 -- field for field, because the whole point of
    # renaming the columns was that content cannot land under the wrong
    # name.
    result = template_result()

    save_hypothesis(factory, bundle_id=bundle_id, result=result)

    assert hypotheses_for_bundle(factory, bundle_id)[0].hypothesis == result.hypothesis


@pytest.mark.database
@requires_database
def test_the_confidence_is_stored_as_one_of_the_three_words(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-001, FR-715 -- the enum spellings were chosen to
    # match this column's check constraint, so a value that validates in
    # Python cannot be refused at write time.
    save_hypothesis(factory, bundle_id=bundle_id, result=template_result())

    with factory.begin() as session:
        stored = session.execute(text("SELECT confidence FROM hypotheses")).scalar_one()

    assert stored in {c.value for c in Confidence}


@pytest.mark.database
@requires_database
def test_a_new_row_starts_new_and_unchecked(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, FR-602, ai-008 -- "New" is a real initial state rather
    # than a placeholder, and "not checked" is the honest grounding value
    # for a row written before the check exists.
    save_hypothesis(factory, bundle_id=bundle_id, result=template_result())

    stored = hypotheses_for_bundle(factory, bundle_id)[0]

    assert stored.status is ReviewStatus.NEW
    assert stored.grounding is GroundingStatus.NOT_CHECKED


@pytest.mark.database
@requires_database
def test_the_write_returns_the_identity_of_the_row_it_made(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- ai-008 has to attach a verdict to one hypothesis and
    # fbk-001 to attach an analyst's, so a write that does not say which
    # row it made forces both of them to guess.
    made = save_hypothesis(factory, bundle_id=bundle_id, result=template_result())

    assert made == hypotheses_for_bundle(factory, bundle_id)[0].id


# --------------------------------------------------------- appending, not replacing


@pytest.mark.database
@requires_database
def test_two_hypotheses_for_one_bundle_are_both_kept(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, db-007 -- and the asymmetry with db-008 is principled:
    # a finding is derived and regenerable from a seed, while a model call
    # consumed money and produced one specific response. Two calls are two
    # facts. One bundle legitimately carries a model hypothesis and the
    # template fallback that replaced it.
    save_hypothesis(factory, bundle_id=bundle_id, result=hosted_result())
    save_hypothesis(factory, bundle_id=bundle_id, result=template_result())

    stored = hypotheses_for_bundle(factory, bundle_id)

    assert [s.generator for s in stored] == [
        GeneratorKind.HOSTED,
        GeneratorKind.TEMPLATE,
    ]


@pytest.mark.database
@requires_database
def test_a_second_call_to_the_same_arm_is_not_a_replacement(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, db-007 -- a retry is a second call with its own cost
    # and its own response, and ai-009 counts calls. Collapsing them would
    # lose the retry rate ai-007 is required to log.
    save_hypothesis(
        factory,
        bundle_id=bundle_id,
        result=hosted_result(raw_response='{"attempt": 1}'),
    )
    save_hypothesis(
        factory,
        bundle_id=bundle_id,
        result=hosted_result(raw_response='{"attempt": 2}'),
    )

    stored = hypotheses_for_bundle(factory, bundle_id)

    assert [s.raw_response for s in stored] == ['{"attempt": 1}', '{"attempt": 2}']


# -------------------------------------------------- refusals at the boundary


@pytest.mark.database
@requires_database
def test_a_hypothesis_for_a_bundle_that_does_not_exist_is_refused(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- a hypothesis explains a bundle, and one pointing at
    # nothing asserts an explanation of an event nobody recorded.
    with pytest.raises((IntegrityError, HypothesisWriteError)):
        save_hypothesis(factory, bundle_id=bundle_id + 9999, result=template_result())


@pytest.mark.database
@requires_database
def test_nothing_is_written_when_the_write_is_refused(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, evb-002 -- the same rule the bundle writer follows: a
    # refusal leaves the database exactly as it was, so a partial row is
    # never left behind to be read as a complete one.
    with pytest.raises(Exception):
        save_hypothesis(factory, bundle_id=bundle_id + 9999, result=template_result())

    assert hypotheses_for_bundle(factory, bundle_id) == []


def test_a_model_arm_row_without_its_model_id_is_refused() -> None:
    # spec: db-002 -- the named failure case, and deliberately a SECOND
    # guard: ai-003 already makes such a result unconstructible, so this
    # holds against a row assembled some other way. Kept because it is the
    # failure nobody can repair after a campaign has run.
    from app.db.hypotheses import check_reproducibility

    with pytest.raises(HypothesisWriteError) as raised:
        check_reproducibility(
            generator=GeneratorKind.HOSTED, model_id=None, raw_response='{"a": 1}'
        )

    assert "hosted" in str(raised.value)


def test_a_model_arm_row_without_its_raw_response_is_refused() -> None:
    # spec: db-002, NFR-602
    from app.db.hypotheses import check_reproducibility

    with pytest.raises(HypothesisWriteError):
        check_reproducibility(
            generator=GeneratorKind.LOCAL, model_id="m-2026", raw_response=None
        )


def test_a_template_row_carrying_a_model_id_is_refused() -> None:
    # spec: db-002 -- the other direction, so the generator column cannot
    # lie either way. A template row naming a model would make the
    # campaign's per-arm counts wrong where nobody would check.
    from app.db.hypotheses import check_reproducibility

    with pytest.raises(HypothesisWriteError) as raised:
        check_reproducibility(
            generator=GeneratorKind.TEMPLATE, model_id="m-2026", raw_response=None
        )

    assert "template" in str(raised.value)


def test_a_template_row_with_neither_is_accepted() -> None:
    # spec: db-002 -- the positive case, without which the rule above is
    # satisfied by refusing everything.
    from app.db.hypotheses import check_reproducibility

    check_reproducibility(
        generator=GeneratorKind.TEMPLATE, model_id=None, raw_response=None
    )


# ------------------------------------------- grounding, in three values not two


def test_not_checked_is_not_the_same_as_failed() -> None:
    # spec: db-002, evb-001 -- the collapse this exists to prevent, stated
    # as behaviour. A bare `bool | None` invites `if not passed:` which
    # treats both alike; an enum makes that unwritable.
    assert GroundingStatus.NOT_CHECKED is not GroundingStatus.FAILED
    assert GroundingStatus.NOT_CHECKED != GroundingStatus.FAILED


@pytest.mark.parametrize(
    "status,stored",
    [
        (GroundingStatus.NOT_CHECKED, None),
        (GroundingStatus.PASSED, True),
        (GroundingStatus.FAILED, False),
    ],
)
def test_each_grounding_state_maps_to_one_stored_value(
    status: GroundingStatus, stored: bool | None
) -> None:
    # spec: db-002 -- three states over a nullable boolean, and the mapping
    # is asserted in both directions so a future column type change cannot
    # quietly merge two of them.
    assert GroundingStatus.from_stored(stored) is status
    assert status.to_stored() is stored


@pytest.mark.database
@requires_database
def test_a_grounding_verdict_round_trips(factory: sessionmaker, bundle_id: int) -> None:
    # spec: db-002, ai-008 -- ai-008 will write this column, so the value
    # it writes has to come back as the state it meant.
    made = save_hypothesis(factory, bundle_id=bundle_id, result=template_result())

    with factory.begin() as session:
        session.execute(
            text("UPDATE hypotheses SET grounding_passed = false WHERE id = :i"),
            {"i": made},
        )

    assert (
        hypotheses_for_bundle(factory, bundle_id)[0].grounding is GroundingStatus.FAILED
    )


# ------------------------------------------------- a bundle's identity, exposed


@pytest.mark.database
@requires_database
def test_a_stored_bundle_can_be_read_back_with_its_identity(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    # spec: db-002, evb-002 -- the blocker found by attempting the write.
    # evb-002's reader returns bundles and no ids, so until now there was
    # no way to say which bundle a hypothesis explains.
    store_a_bundle(migrated_database, factory)

    stored = stored_bundles_for_run(factory, RUN_ID)

    assert len(stored) == 1
    assert isinstance(stored[0][0], int)
    assert stored[0][1].subject == zone_bundle(tracks=False).subject


@pytest.mark.database
@requires_database
def test_exposing_the_identity_did_not_change_what_the_reader_returns(
    migrated_database: Engine, factory: sessionmaker
) -> None:
    # spec: db-002, evb-002 -- evb-002's own reader and two measurements
    # depend on the existing return shape, so the new function is beside
    # it rather than a change to it.
    from app.db.bundles import bundles_for_run

    store_a_bundle(migrated_database, factory)

    assert bundles_for_run(factory, RUN_ID) == [
        bundle for _, bundle in stored_bundles_for_run(factory, RUN_ID)
    ]
