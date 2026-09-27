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

Two more, added 2026-09-27 and both found by building `ai-012`, the
campaign that would be this module's first real caller.

**The three-valued column had no writer for two of its three values.** The
write hard-coded *not yet checked* and nothing came back afterwards, so a
campaign would have stored every verdict it held in its hand nowhere. The
typed absence was built correctly and then never filled, which is worse
than the two-valued flag it replaced: the column now looks capable of the
distinction while the data never makes it.

**A row said which generator answered and not which arm was asked.** They
differ exactly once, and it is the case that matters: when the model arm
falls back, the stored template row is byte-identical to the template
baseline's own row for the same bundle. Two identical rows, one of them the
model arm's delivery, and nothing to tell them apart -- so a fallback is
invisible in the data, the per-arm figures are ambiguous at the rows that
carry the most weight, and `ai-010`'s screen indicator is unbuildable
rather than merely unbuilt.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.ai.grounding import GroundingReport, check
from app.ai.hypothesis import Confidence, Hypothesis
from app.ai.service import GenerationResult, GeneratorKind, ModelCall, Usage
from app.ai.template import generate as template_generate
from app.db.bundles import save_bundles, stored_bundles_for_run
from app.db.hypotheses import (
    GroundingStatus,
    HypothesisWriteError,
    ReviewStatus,
    check_requested_arm,
    hypotheses_for_bundle,
    record_grounding,
    save_hypothesis,
)
from app.db.migrations import alembic_config
from tests.conftest import requires_database
from tests.test_ai_grounding import citing
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


OTHER_RUN_ID = RUN_ID + 1


@pytest.fixture
def neighbours(migrated_database: Engine, factory: sessionmaker) -> dict[str, int]:
    """Two bundles in this run and one in another, each with a hypothesis.

    Every one of these exists because a mutation survived without them.
    Three of `db-002`'s five genuine gaps were scoping or ordering rules,
    which is the third time a pass over this project has found exactly that
    family: the suites test thoroughly what goes in and barely what must
    stay out.
    """
    from dataclasses import replace

    # The run first: observations carry a NOT NULL foreign key to it.
    with migrated_database.connect() as connection:
        connection.execute(text(
            "INSERT INTO scenario_runs "
            "(id, scenario_type, parameters, seed, started_at) "
            "VALUES (:id, 'rf-sensor-fault', '{}'::jsonb, 43, now())"),
            {"id": OTHER_RUN_ID})
        connection.commit()
    for sensor in ("RF-03", "RF-04"):
        insert_rf(migrated_database, run_id=RUN_ID, sensor=sensor, channel=4, at=START)
        insert_rf(migrated_database, run_id=OTHER_RUN_ID, sensor=sensor, channel=4,
                  at=START)

    # One call, two bundles: save_bundles replaces per run, so two calls
    # would leave only the second.
    save_bundles(factory, scenario_run_id=RUN_ID, bundles=[
        replace(zone_bundle(tracks=False), scenario_run_id=RUN_ID),
        replace(fault_bundle(), scenario_run_id=RUN_ID),
    ])
    save_bundles(factory, scenario_run_id=OTHER_RUN_ID, bundles=[
        replace(zone_bundle(tracks=False), scenario_run_id=OTHER_RUN_ID)])

    here = stored_bundles_for_run(factory, RUN_ID)
    there = stored_bundles_for_run(factory, OTHER_RUN_ID)
    ids = {"first": here[0][0], "second": here[1][0], "other_run": there[0][0]}

    store(factory, bundle_id=ids["second"], result=template_result())
    store(factory, bundle_id=ids["other_run"], result=template_result())
    return ids


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


def store(
    factory: sessionmaker,
    *,
    bundle_id: int,
    result: GenerationResult,
    requested: GeneratorKind | None = None,
) -> int:
    """`save_hypothesis`, with the asked-for arm defaulting to the answering one.

    The default lives **here and not in the writer**: the argument has no
    default in `app/`, and a separate test holds that, because the one
    caller most likely to get it wrong is the one where the two values
    differ. In a test that is about something else, the two coincide, and
    saying so twenty-one times would bury what each test is for.
    """
    return save_hypothesis(
        factory,
        bundle_id=bundle_id,
        result=result,
        requested_generator=result.generator if requested is None else requested,
    )


def passing_report() -> GroundingReport:
    """A real verdict on a hypothesis that is grounded by construction."""
    return check(a_hypothesis(), fault_bundle())


def failing_report() -> GroundingReport:
    """A real verdict on a hypothesis citing a rule the bundle does not carry."""
    bundle = fault_bundle()
    return check(citing(bundle, ("NOT-A-RULE", "not_a_finding")), bundle)


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
    store(factory, bundle_id=bundle_id, result=template_result())

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
    store(factory, bundle_id=bundle_id, result=template_result())

    with factory.begin() as session:
        session.execute(text("UPDATE hypotheses SET status = :s"), {"s": status})


@pytest.mark.database
@requires_database
def test_the_revision_is_reversible(migrated_database: Engine) -> None:
    # spec: db-002, db-010 -- a rename and two added columns are exactly the
    # kind of change that must be undoable. The target revision is NAMED,
    # not counted: the equivalent test for evb-002 used "one step back from
    # head" and silently began testing a different revision the moment this
    # one was added.
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url",
        migrated_database.url.render_as_string(hide_password=False),
    )

    # At head first, or the downgrade half passes against any revision that
    # never made the change.
    assert "summary" in column_names(migrated_database)
    assert "title" not in column_names(migrated_database)

    command.downgrade(config, "0005_evidence_bundle_columns")

    columns = column_names(migrated_database)
    assert "summary" not in columns
    assert "recommended_human_action" not in columns
    assert "title" in columns, "the old name did not come back"
    assert "hypotheses" in _tables(migrated_database), \
        "the downgrade took the table with it"

    command.upgrade(config, "head")

    assert "summary" in column_names(migrated_database)
    assert "hypothesis_title" in column_names(migrated_database)


def _tables(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return {
            row[0] for row in connection.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"))
        }


# ------------------------------------------------------------------- the write


@pytest.mark.database
@requires_database
def test_a_template_hypothesis_is_stored_with_no_model_behind_it(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-002
    store(factory, bundle_id=bundle_id, result=template_result())

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

    store(factory, bundle_id=bundle_id, result=result)
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

    store(
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

    store(factory, bundle_id=bundle_id, result=result)

    assert hypotheses_for_bundle(factory, bundle_id)[0].hypothesis == result.hypothesis


@pytest.mark.database
@requires_database
def test_the_confidence_is_stored_as_one_of_the_three_words(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-001, FR-715 -- the enum spellings were chosen to
    # match this column's check constraint, so a value that validates in
    # Python cannot be refused at write time.
    store(factory, bundle_id=bundle_id, result=template_result())

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
    store(factory, bundle_id=bundle_id, result=template_result())

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
    made = store(factory, bundle_id=bundle_id, result=template_result())

    assert made == hypotheses_for_bundle(factory, bundle_id)[0].id


@pytest.mark.database
@requires_database
def test_a_template_row_stores_no_parameters_rather_than_a_json_null(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- found by mutation, and invisible from Python: a JSONB
    # `null` reads back as None exactly like SQL NULL, so the round trip
    # cannot tell them apart. They are different facts about the column --
    # "no parameter set was recorded" against "a parameter set was recorded
    # and it was null" -- and only the first is true of an arm with no model.
    store(factory, bundle_id=bundle_id, result=template_result())

    with factory.begin() as session:
        sql_null, json_null = session.execute(text(
            "SELECT generation_params IS NULL, "
            "  generation_params = 'null'::jsonb "
            "FROM hypotheses")).one()

    assert sql_null is True
    assert json_null is None, "a JSONB null would compare, not return NULL"


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
    store(factory, bundle_id=bundle_id, result=hosted_result())
    store(factory, bundle_id=bundle_id, result=template_result())

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
    store(
        factory,
        bundle_id=bundle_id,
        result=hosted_result(raw_response='{"attempt": 1}'),
    )
    store(
        factory,
        bundle_id=bundle_id,
        result=hosted_result(raw_response='{"attempt": 2}'),
    )

    stored = hypotheses_for_bundle(factory, bundle_id)

    assert [s.raw_response for s in stored] == ['{"attempt": 1}', '{"attempt": 2}']


@pytest.mark.database
@requires_database
def test_only_this_bundle_s_hypotheses_come_back(
    factory: sessionmaker, neighbours: dict[str, int]
) -> None:
    # spec: db-002, evb-001 -- found by mutation. Every earlier test had one
    # bundle in the database, so dropping the WHERE clause changed nothing
    # any of them could see. A hypothesis attached to the wrong event is not
    # malformed, it is wrong.
    store(factory, bundle_id=neighbours["first"], result=template_result())

    stored = hypotheses_for_bundle(factory, neighbours["first"])

    assert len(stored) == 1
    assert stored[0].bundle_id == neighbours["first"]


@pytest.mark.database
@requires_database
def test_a_hypothesis_from_another_run_never_reaches_this_bundle(
    factory: sessionmaker, neighbours: dict[str, int]
) -> None:
    # spec: db-002 -- the same rule across runs rather than across bundles,
    # because the uniqueness everything here rests on is uniqueness WITHIN
    # one run and the same coordinates exist in all 300.
    stored = hypotheses_for_bundle(factory, neighbours["second"])

    assert [s.bundle_id for s in stored] == [neighbours["second"]]


@pytest.mark.database
@requires_database
def test_hypotheses_come_back_in_the_order_they_were_written(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, NFR-601 -- found by mutation, and the ordering had to be
    # DISTURBED to see it: with a handful of untouched rows a sequential
    # scan returns them in insertion order anyway, so dropping ORDER BY
    # changed nothing. Updating a row rewrites it to the end of the heap
    # under MVCC, which is what makes physical order differ from id order.
    made = [store(factory, bundle_id=bundle_id, result=hosted_result(
        raw_response=f'{{"attempt": {n}}}')) for n in range(4)]

    with factory.begin() as session:
        session.execute(text(
            "UPDATE hypotheses SET summary = summary || :s WHERE id = :i"),
            {"s": " (revised)", "i": made[0]})

    assert [s.id for s in hypotheses_for_bundle(factory, bundle_id)] == made


@pytest.mark.database
@requires_database
def test_the_bundle_reader_is_scoped_to_its_run(
    factory: sessionmaker, neighbours: dict[str, int]
) -> None:
    # spec: db-002, evb-002 -- found by mutation on the reader this item
    # added. Every test of it had one run in the database.
    here = stored_bundles_for_run(factory, RUN_ID)
    there = stored_bundles_for_run(factory, OTHER_RUN_ID)

    assert len(here) == 2
    assert len(there) == 1
    assert {i for i, _ in here}.isdisjoint({i for i, _ in there})
    assert all(bundle.scenario_run_id == RUN_ID for _, bundle in here)


# -------------------------------------------------- refusals at the boundary


@pytest.mark.database
@requires_database
def test_a_hypothesis_for_a_bundle_that_does_not_exist_is_refused(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- a hypothesis explains a bundle, and one pointing at
    # nothing asserts an explanation of an event nobody recorded.
    with pytest.raises((IntegrityError, HypothesisWriteError)):
        store(factory, bundle_id=bundle_id + 9999, result=template_result())


@pytest.mark.database
@requires_database
def test_nothing_is_written_when_the_write_is_refused(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, evb-002 -- the same rule the bundle writer follows: a
    # refusal leaves the database exactly as it was, so a partial row is
    # never left behind to be read as a complete one.
    with pytest.raises(Exception):
        store(factory, bundle_id=bundle_id + 9999, result=template_result())

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


def test_a_blank_model_id_does_not_count_as_present() -> None:
    # spec: db-002 -- found by mutation: the suite passed None and never an
    # empty string, so a guard reading `is None` survived. An empty model id
    # satisfies a check for "populated" while naming nothing, which is the
    # same distinction ai-003's ModelCall already draws one layer up.
    from app.db.hypotheses import check_reproducibility

    for blank in ("", "   "):
        with pytest.raises(HypothesisWriteError):
            check_reproducibility(generator=GeneratorKind.HOSTED, model_id=blank,
                                  raw_response='{"a": 1}')


def test_a_blank_raw_response_does_not_count_as_present() -> None:
    # spec: db-002, NFR-602 -- the same hole on the other field.
    from app.db.hypotheses import check_reproducibility

    with pytest.raises(HypothesisWriteError):
        check_reproducibility(generator=GeneratorKind.LOCAL, model_id="m-2026",
                              raw_response="   ")


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
    made = store(factory, bundle_id=bundle_id, result=template_result())

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


# ------------------------------- which arm was asked, not only which answered


@pytest.mark.database
@requires_database
def test_the_row_says_which_arm_was_asked(migrated_database: Engine) -> None:
    # spec: db-002, ai-010, ai-012 -- the column the fallback is invisible
    # without. NOT NULL and no default: a row that acquired the value by
    # omission would say the arm asked was the one that answered, which is
    # false precisely when it matters.
    assert "requested_generator" in column_names(migrated_database)
    assert not is_nullable(migrated_database, "requested_generator")


@pytest.mark.database
@requires_database
def test_an_unknown_asked_for_arm_is_refused_by_the_database(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- the same vocabulary and the same kind of constraint
    # the `generator` column beside it has carried since 0001. Semantics go
    # at the repository boundary; the vocabulary goes here.
    store(factory, bundle_id=bundle_id, result=template_result())

    with pytest.raises(DBAPIError):
        with factory.begin() as session:
            session.execute(text("UPDATE hypotheses SET requested_generator = 'gpt'"))


@pytest.mark.database
@requires_database
def test_every_generator_kind_is_accepted_as_the_arm_that_was_asked(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-006 -- read off the enum rather than listed here, so
    # a fourth arm fails this instead of being refused by the database at
    # the moment a campaign runs.
    store(factory, bundle_id=bundle_id, result=template_result())

    for kind in GeneratorKind:
        with factory.begin() as session:
            session.execute(
                text("UPDATE hypotheses SET requested_generator = :k"),
                {"k": kind.value},
            )


def test_the_arm_that_was_asked_has_no_default() -> None:
    # spec: db-002, ai-003 -- `GenerationConfig.model_id`'s rule. A default
    # would be `result.generator`, which is right on every row except the
    # fallback ones, and those are the only rows this column exists for.
    parameter = inspect.signature(save_hypothesis).parameters["requested_generator"]

    assert parameter.default is inspect.Parameter.empty


@pytest.mark.database
@requires_database
def test_a_primary_arm_row_records_both_and_reports_no_fallback(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-012 -- the ordinary case: the arm that was asked
    # answered.
    store(factory, bundle_id=bundle_id, result=hosted_result())

    stored = hypotheses_for_bundle(factory, bundle_id)[0]

    assert stored.generator is GeneratorKind.HOSTED
    assert stored.requested_generator is GeneratorKind.HOSTED
    assert stored.fell_back is False


@pytest.mark.database
@requires_database
def test_a_fallback_row_records_the_arm_that_was_asked(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-007, ai-012 -- the model was asked and the template
    # answered, which is what a correctness fallback is. The value is not
    # derived from the result, or this row would claim the template was the
    # configured arm.
    store(
        factory,
        bundle_id=bundle_id,
        result=template_result(),
        requested=GeneratorKind.HOSTED,
    )

    stored = hypotheses_for_bundle(factory, bundle_id)[0]

    assert stored.generator is GeneratorKind.TEMPLATE
    assert stored.requested_generator is GeneratorKind.HOSTED
    assert stored.fell_back is True


@pytest.mark.database
@requires_database
def test_a_fallback_is_distinguishable_from_the_baseline_that_shares_its_text(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-012, eval-005 -- the defect this column exists for,
    # written as the campaign will produce it. One bundle, two template
    # rows: the hosted arm's delivery after a grounding failure, and the
    # template arm's own baseline. The hypotheses are byte-identical because
    # the same deterministic generator wrote both, so before this column
    # the two rows differed in nothing at all and a per-arm count had to
    # guess which was which.
    store(
        factory,
        bundle_id=bundle_id,
        result=template_result(),
        requested=GeneratorKind.HOSTED,
    )
    store(factory, bundle_id=bundle_id, result=template_result())

    fallback, baseline = hypotheses_for_bundle(factory, bundle_id)

    assert fallback.hypothesis == baseline.hypothesis, "the texts are the same"
    assert fallback.generator is baseline.generator is GeneratorKind.TEMPLATE
    assert fallback.requested_generator is GeneratorKind.HOSTED
    assert baseline.requested_generator is GeneratorKind.TEMPLATE
    assert [row.fell_back for row in (fallback, baseline)] == [True, False]


def test_the_template_cannot_be_the_arm_that_asked_a_model() -> None:
    # spec: db-002, ai-009 -- the one direction that is not a fallback but
    # nonsense. Both fallbacks run towards the template: ai-007 goes
    # model-to-template and ai-006 hosted-to-local, and nothing falls back
    # *from* an arm that makes no call. Refused at the boundary, where the
    # combination is known, rather than in the database, which holds the
    # vocabulary.
    for answered in (GeneratorKind.HOSTED, GeneratorKind.LOCAL):
        with pytest.raises(HypothesisWriteError, match="makes no call"):
            check_requested_arm(
                generator=answered, requested_generator=GeneratorKind.TEMPLATE
            )


def test_every_fallback_direction_that_can_really_happen_is_accepted() -> None:
    # spec: db-002, ai-006, ai-007 -- a guard that refused these would
    # refuse the rows the column was added for. ai-007 ends at the
    # template from either model arm; ai-006 ends at the local arm from
    # the hosted one.
    for answered, asked in (
        (GeneratorKind.TEMPLATE, GeneratorKind.HOSTED),
        (GeneratorKind.TEMPLATE, GeneratorKind.LOCAL),
        (GeneratorKind.LOCAL, GeneratorKind.HOSTED),
        (GeneratorKind.HOSTED, GeneratorKind.HOSTED),
        (GeneratorKind.TEMPLATE, GeneratorKind.TEMPLATE),
    ):
        check_requested_arm(generator=answered, requested_generator=asked)


@pytest.mark.database
@requires_database
def test_a_row_claiming_the_template_asked_a_model_is_refused_before_it_is_written(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- the boundary refusal reached through the writer, not
    # only through the function under it, and nothing left behind.
    with pytest.raises(HypothesisWriteError):
        save_hypothesis(
            factory,
            bundle_id=bundle_id,
            result=hosted_result(),
            requested_generator=GeneratorKind.TEMPLATE,
        )

    assert hypotheses_for_bundle(factory, bundle_id) == []


@pytest.mark.database
@requires_database
def test_the_asked_for_arm_revision_is_reversible(migrated_database: Engine) -> None:
    # spec: db-002, db-010 -- the target revision is NAMED rather than
    # counted, because the equivalent test for evb-002 used "one step back
    # from head" and silently began testing a different revision the moment
    # a new one landed.
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url",
        migrated_database.url.render_as_string(hide_password=False),
    )
    assert "requested_generator" in column_names(migrated_database)

    command.downgrade(config, "0006_hypothesis_columns")

    assert "requested_generator" not in column_names(migrated_database)
    assert "hypotheses" in _tables(migrated_database), \
        "the downgrade took the table with it"
    assert "summary" in column_names(migrated_database), \
        "the downgrade went further back than the revision it was given"

    command.upgrade(config, "head")

    assert "requested_generator" in column_names(migrated_database)


# --------------------------------------------- the verdict, written where it belongs


@pytest.mark.database
@requires_database
def test_a_passing_verdict_is_recorded_against_the_row(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-008 -- the value the column could hold and nothing
    # could write. Without this a campaign stores every verdict nowhere.
    made = store(factory, bundle_id=bundle_id, result=template_result())

    record_grounding(factory, hypothesis_id=made, report=passing_report())

    assert hypotheses_for_bundle(factory, bundle_id)[0].grounding is (
        GroundingStatus.PASSED
    )


@pytest.mark.database
@requires_database
def test_a_failing_verdict_is_recorded_as_failed_and_not_as_unchecked(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-008, evb-001 -- the collapse this column exists to
    # prevent, now reachable through the writer: a failed check must not
    # arrive as "never checked", which is what `if not passed` would store.
    made = store(factory, bundle_id=bundle_id, result=template_result())
    report = failing_report()
    assert not report.passed, "the fixture stopped exercising a failure"

    record_grounding(factory, hypothesis_id=made, report=report)

    assert hypotheses_for_bundle(factory, bundle_id)[0].grounding is (
        GroundingStatus.FAILED
    )


@pytest.mark.database
@requires_database
def test_no_verdict_leaves_the_row_unchecked(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, ai-008 -- there is no third value to write, because the
    # parameter is ai-008's report and a report has two outcomes. The spec
    # asks for "not checked" to be refused; it is unconstructible instead,
    # following ai-011's preference for the bad state that cannot be
    # expressed over the one that is turned away.
    for report in (passing_report(), failing_report()):
        made = store(factory, bundle_id=bundle_id, result=template_result())

        record_grounding(factory, hypothesis_id=made, report=report)

        stored = {row.id: row for row in hypotheses_for_bundle(factory, bundle_id)}
        assert stored[made].grounding is not GroundingStatus.NOT_CHECKED


@pytest.mark.database
@requires_database
def test_a_verdict_touches_only_the_row_it_names(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- scoping, which is the family of gap a pass over this
    # project has now found three times: the suites test thoroughly what
    # goes in and barely what must stay out. An unscoped UPDATE would mark
    # every hypothesis in the table with one bundle's verdict.
    first = store(factory, bundle_id=bundle_id, result=template_result())
    second = store(factory, bundle_id=bundle_id, result=hosted_result())

    record_grounding(factory, hypothesis_id=first, report=failing_report())

    rows = {row.id: row.grounding for row in hypotheses_for_bundle(factory, bundle_id)}
    assert rows[first] is GroundingStatus.FAILED
    assert rows[second] is GroundingStatus.NOT_CHECKED


@pytest.mark.database
@requires_database
def test_a_verdict_against_a_row_that_does_not_exist_is_refused(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002 -- a verdict written to no row and a verdict written are
    # indistinguishable to the caller unless the writer says so, and the
    # caller here is a campaign that has already spent the money.
    made = store(factory, bundle_id=bundle_id, result=template_result())

    with pytest.raises(HypothesisWriteError, match="no hypothesis"):
        record_grounding(factory, hypothesis_id=made + 9999, report=passing_report())

    assert hypotheses_for_bundle(factory, bundle_id)[0].grounding is (
        GroundingStatus.NOT_CHECKED
    )


@pytest.mark.database
@requires_database
def test_a_verdict_does_not_disturb_the_review_status(
    factory: sessionmaker, bundle_id: int
) -> None:
    # spec: db-002, FR-602, fbk-001 -- the grounding verdict is the
    # machine's and the status is the analyst's. A write that reset the
    # status would discard an analyst's judgement on any row the campaign
    # re-checked.
    made = store(factory, bundle_id=bundle_id, result=template_result())
    with factory.begin() as session:
        session.execute(
            text("UPDATE hypotheses SET status = :s WHERE id = :i"),
            {"s": ReviewStatus.CONFIRMED.value, "i": made},
        )

    record_grounding(factory, hypothesis_id=made, report=passing_report())

    stored = hypotheses_for_bundle(factory, bundle_id)[0]
    assert stored.status is ReviewStatus.CONFIRMED
    assert stored.grounding is GroundingStatus.PASSED
