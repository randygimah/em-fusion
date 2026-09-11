"""The synthetic RF adapter: one run's grid through the DAL. Spec: adp-002.

`scn-001` emits the stream in memory and `scn-002` decides what is wrong with
it. Neither writes anything down. This is the driver that carries a run's grid
through the single ingest entrypoint into the repository, and it is the body
`scn-003`'s batch executes -- which is why these tests care about three things
an in-memory item never had to:

* **What the store holds is what the emitter produced.** The adapter is a
  driver and nothing else, so any difference between the stream and the rows is
  a defect in it rather than a transformation it is entitled to make.
* **The whole grid arrives, or none of it does.** The unit of work is one run,
  deliberately unlike `adp-007`'s window: a run that wrote half its grid and was
  then skipped by the batch would still be counted as evidence.
* **Nothing in the store says what was staged.** `scn-002` asserted `api-009`
  against the in-memory stream. Persistence is a second surface, and an answer
  key that leaks from the database leaks to every detector that reads it.

The live-database tier is marked and skips without `TEST_DATABASE_URL`. Its
atomicity test induces a real foreign-key violation rather than patching the
repository, following `db-003`: a driver that opened two transactions would pass
against a fake that raised on the second call.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.adapters import synthetic_rf
from app.adapters.synthetic_rf import emit_run
from app.dal.models import (
    CanonicalObservation,
    DataMode,
    ObservationType,
    RfPayload,
    SourceType,
)
from app.dal.pseudonymise import Pseudonymiser
from app.db.migrations import alembic_config
from app.db.repository import PostgisObservationRepository
from app.scenario.emitter import (
    BaselineParameters,
    RunSpec,
    emit_baseline,
    emit_rf,
    stream_digest,
    ticks,
)
from app.scenario.incident import IncidentParameters, ScenarioType, plan_incident
from app.scenario.layout import RfLayout, load_layout
from tests.conftest import requires_database
from tests.fakes import FailingObservationRepository, InMemoryObservationRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]

SEED = 20220627
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)

#: A minute at the layout's ten-second interval: six ticks, enough for the grid
#: to have a shape without making the live tier write a run's worth of rows to
#: prove a property that holds at six.
DURATION_SECONDS = 60

#: The run every observation belongs to. Both tables carry a NOT NULL foreign
#: key to `scenario_runs`, and creating that row is `scn-003`'s job, not this
#: adapter's -- which is what the live fixture below exists to show.
RUN_ID = 1

#: Absent from `scenario_runs`, so writing against it violates the foreign key.
#: A real database failure, rather than a simulated one.
MISSING_RUN_ID = 9999

#: Never the corpus seed (`dal-004`). Two different values, because "the
#: pseudonym seed changes nothing on this side" is a claim that needs two.
PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")
OTHER_PSEUDONYMISER = Pseudonymiser(seed="a-different-test-seed")


@pytest.fixture()
def layout() -> RfLayout:
    return load_layout()


@pytest.fixture()
def repository() -> InMemoryObservationRepository:
    return InMemoryObservationRepository()


def _spec(
    *,
    scenario_type: ScenarioType = ScenarioType.GNSS_DEGRADATION,
    seed: int = SEED,
    duration_seconds: int = DURATION_SECONDS,
) -> RunSpec:
    return RunSpec(
        scenario_type=scenario_type,
        parameters=BaselineParameters(),
        incident=IncidentParameters(start_offset_s=10, duration_s=30),
        seed=seed,
        start=START,
        duration_seconds=duration_seconds,
    )


def _grid_size(layout: RfLayout, spec: RunSpec) -> int:
    return len(layout.sensors) * len(layout.channels) * len(ticks(layout, spec))


def _digest(observations: Iterable[CanonicalObservation]) -> str:
    """The stored stream in the same canonical form `scn-001` digests.

    Reuses the committed serialisation rather than inventing a second one, so
    "the same run stores the same stream" is the same claim as "the same run
    emits the same stream", measured one layer further down.
    """
    return stream_digest(
        [
            {"timestamp": observation.timestamp, **observation.payload.model_dump()}
            for observation in observations
        ]
    )


def _strings(value: Any) -> Iterator[str]:
    """Every string anywhere inside a nested structure.

    Parsed rather than scrubbed. A substring search over a serialised record
    matched `on_ground` against the word "ground" once already; walking the
    structure and comparing whole values cannot repeat it.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _imports(module: Any) -> set[str]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


# ------------------------------------ the stream reaches the store unaltered


def test_a_run_becomes_canonical_rf_observations(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    # spec: adp-002
    spec = _spec()

    result = emit_run(layout, spec, RUN_ID, repository, PSEUDONYMISER)

    assert result.accepted == _grid_size(layout, spec)
    assert result.quarantined == 0
    assert all(
        observation.observation_type is ObservationType.RF
        and observation.source_type is SourceType.SYNTHETIC_RF
        and isinstance(observation.payload, RfPayload)
        for observation in repository.observations
    )


def test_the_grid_is_dense_in_the_store(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    """The second failure case, re-asserted after persistence.

    A sparse grid is invisible to a count alone -- one cell twice and another
    missing balances perfectly -- so the coordinates are compared as a set.
    """
    # spec: adp-002
    spec = _spec()

    emit_run(layout, spec, RUN_ID, repository, PSEUDONYMISER)

    cells = [
        (
            observation.timestamp,
            observation.payload.sensor_id,
            observation.payload.channel_index,
        )
        for observation in repository.observations
    ]
    expected = {
        (tick, sensor.sensor_id, channel.index)
        for tick in ticks(layout, spec)
        for sensor in layout.sensors
        for channel in layout.channels
    }

    assert len(cells) == len(expected)
    assert set(cells) == expected


def test_the_counts_balance_against_the_emitted_stream(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    """`dal-002`'s nothing-is-silently-dropped guarantee, as arithmetic."""
    # spec: adp-002, dal-002
    spec = _spec()
    emitted = len(emit_rf(layout, spec, plan_incident(layout, spec)))

    result = emit_run(layout, spec, RUN_ID, repository, PSEUDONYMISER)

    assert result.accepted + result.quarantined == emitted


def test_the_adapter_alters_no_reading(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    """A driver, not a transformer: every field arrives as the emitter set it."""
    # spec: adp-002
    spec = _spec()
    emitted = emit_rf(layout, spec, plan_incident(layout, spec))

    emit_run(layout, spec, RUN_ID, repository, PSEUDONYMISER)

    stored = repository.observations
    assert len(stored) == len(emitted)
    for observation, record in zip(stored, emitted, strict=True):
        assert observation.timestamp == record["timestamp"]
        assert observation.location.model_dump() == record["location"]
        assert observation.payload.model_dump() == record["payload"]


# ----------------------------------------------- provenance and the data mode


def test_every_observation_is_marked_synthetic(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    """`op-001`'s badge reads this field, so a mislabelled row makes the
    interface lie about what the analyst is looking at."""
    # spec: adp-002, op-001
    emit_run(layout, _spec(), RUN_ID, repository, PSEUDONYMISER)

    assert {observation.data_mode for observation in repository.observations} == {
        DataMode.SYNTHETIC
    }
    assert {
        observation.provenance.data_mode for observation in repository.observations
    } == {DataMode.SYNTHETIC}


def test_every_observation_belongs_to_the_run_it_was_emitted_for(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    # spec: adp-002, dal-003
    emit_run(layout, _spec(), RUN_ID, repository, PSEUDONYMISER)

    assert {
        observation.provenance.scenario_run_id
        for observation in repository.observations
    } == {RUN_ID}


def test_the_adapter_cannot_mark_a_run_replayed() -> None:
    """The first failure case, closed by construction rather than checked.

    The context is built inside the adapter from the one mode a synthetic
    source may claim, so there is no argument a caller could pass to get a
    replayed row out of it. Read from the parsed source: the claim is that the
    other member is never referenced at all.
    """
    # spec: adp-002
    tree = ast.parse(Path(synthetic_rf.__file__).read_text(encoding="utf-8"))
    referenced = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert "SYNTHETIC" in referenced
    assert "REPLAYED" not in referenced


# ------------------------------------------------ determinism through the DAL


def test_the_same_seed_stores_the_same_stream(layout: RfLayout) -> None:
    """`adp-002`'s own first failure case, measured on the stored rows rather
    than on the stream that produced them."""
    # spec: adp-002, scn-001
    first = InMemoryObservationRepository()
    second = InMemoryObservationRepository()

    emit_run(layout, _spec(), RUN_ID, first, PSEUDONYMISER)
    emit_run(layout, _spec(), RUN_ID, second, PSEUDONYMISER)

    assert _digest(first.observations) == _digest(second.observations)


def test_a_different_seed_stores_a_different_stream(layout: RfLayout) -> None:
    """The trap arm: an adapter that ignored the seed would pass the test
    above and be useless."""
    # spec: adp-002, scn-001
    first = InMemoryObservationRepository()
    second = InMemoryObservationRepository()

    emit_run(layout, _spec(seed=SEED), RUN_ID, first, PSEUDONYMISER)
    emit_run(layout, _spec(seed=SEED + 1), RUN_ID, second, PSEUDONYMISER)

    assert _digest(first.observations) != _digest(second.observations)


def test_the_stored_stream_does_not_depend_on_the_pseudonym_seed(
    layout: RfLayout,
) -> None:
    """The pseudonymiser is carried and unused: `IDENTIFIER_RULES` has no RF
    entry, so two different seeds must produce identical rows. If this ever
    fails, an RF field has acquired an identity the DAL is rewriting."""
    # spec: adp-002, dal-004
    first = InMemoryObservationRepository()
    second = InMemoryObservationRepository()

    emit_run(layout, _spec(), RUN_ID, first, PSEUDONYMISER)
    emit_run(layout, _spec(), RUN_ID, second, OTHER_PSEUDONYMISER)

    assert _digest(first.observations) == _digest(second.observations)


# --------------------------------------------------- the run stages itself


def test_a_staged_run_is_stored_staged(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    """The caller supplies a spec, not an incident.

    Planning it here rather than accepting one makes a mismatch between a run's
    observations and its answer key impossible: a caller that forgot to plan
    would otherwise write a quiet grid under a run row claiming interference.
    """
    # spec: adp-002, scn-002
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)

    emit_run(layout, spec, RUN_ID, repository, PSEUDONYMISER)

    assert _digest(repository.observations) != stream_digest(
        emit_baseline(layout, spec)
    )


def test_a_baseline_run_is_stored_quiet(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    """The other half of the same claim, and `anom-008`'s control: the clean
    type must store exactly the quiet stream, byte for byte."""
    # spec: adp-002, scn-002
    spec = _spec(scenario_type=ScenarioType.NORMAL_BASELINE)

    emit_run(layout, spec, RUN_ID, repository, PSEUDONYMISER)

    assert _digest(repository.observations) == stream_digest(
        emit_baseline(layout, spec)
    )


def test_no_stored_observation_carries_the_scenario_type(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    """`api-009` on the persistence surface. Two checks, because either alone
    is weak: the payload's fields are exactly `RfPayload`'s, and no string
    anywhere in the row is one of the five type names."""
    # spec: adp-002, api-009
    emit_run(layout, _spec(), RUN_ID, repository, PSEUDONYMISER)

    type_names = {member.value for member in ScenarioType}
    for observation in repository.observations:
        assert set(observation.payload.model_dump()) == set(RfPayload.model_fields)
        assert not type_names & set(_strings(observation.model_dump(mode="json")))
        assert "ground_truth" not in set(_strings(observation.model_dump(mode="json")))


# --------------------------------------------------- the unit of work is a run


def test_one_run_is_one_batch(
    layout: RfLayout, repository: InMemoryObservationRepository
) -> None:
    """Deliberately unlike `adp-007`, which tiles a replay into windows. A
    synthetic run regenerates from its seed, so all-or-nothing at run scale
    costs nothing to retry -- and a half-written run that the batch then skips
    would still be read as evidence."""
    # spec: adp-002, dal-002
    emit_run(layout, _spec(), RUN_ID, repository, PSEUDONYMISER)

    assert repository.calls == 1


def test_a_failed_write_stores_nothing(layout: RfLayout) -> None:
    """The failure is reported, not swallowed: `scn-003` can only record and
    skip a run that told it something went wrong."""
    # spec: adp-002, scn-003
    repository = FailingObservationRepository()

    # Matched on the message rather than the type alone: `NotImplementedError`
    # is a `RuntimeError`, so the looser form passed against the stub this file
    # was proven red against.
    with pytest.raises(RuntimeError, match="not having it"):
        emit_run(layout, _spec(), RUN_ID, repository, PSEUDONYMISER)

    assert repository.observations == []
    assert repository.calls == 1


# ------------------------------------------------ what this adapter does not do


def test_the_adapter_invents_no_numbers() -> None:
    """The stream is `scn-001`'s and stays there. An adapter that derived a
    reading of its own would be a second generator, outside everything
    `scn-001` proves about determinism."""
    # spec: adp-002, scn-001
    imported = _imports(synthetic_rf)

    assert "random" not in imported
    assert "secrets" not in imported
    assert "hashlib" not in imported
    assert not [name for name in imported if name.startswith("app.scenario.seeding")]


def test_the_adapter_holds_no_sql_and_no_run_lifecycle() -> None:
    """The fifth decision: it is handed a run id and writes observations under
    it. Creating the run, recording ground truth and marking completion belong
    to the producer of the run (`scn-003`, `db-007`)."""
    # spec: adp-002, db-007
    tree = ast.parse(Path(synthetic_rf.__file__).read_text(encoding="utf-8"))
    imported = _imports(synthetic_rf)
    defined = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    assert "sqlalchemy" not in {name.split(".")[0] for name in imported}
    for name in ("create_scenario_run", "record_ground_truth", "complete_scenario_run"):
        assert name not in defined
        assert not hasattr(synthetic_rf, name)


# ------------------------------------------------------------- live database


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    """An empty schema at head, holding one scenario run.

    The run is inserted here rather than by the adapter, which is the point of
    the fifth decision: an adapter that quietly created its own parent row
    would hide the constraint the atomicity test below relies on.
    """
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
                "VALUES (:id, 'gnss-degradation', '{}'::jsonb, :seed, now())"
            ),
            {"id": RUN_ID, "seed": SEED},
        )
        connection.commit()
    return empty_database


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        )


@pytest.mark.database
@requires_database
def test_a_run_lands_in_postgis(layout: RfLayout, migrated_database: Engine) -> None:
    # spec: adp-002, db-003
    spec = _spec()
    repository = PostgisObservationRepository(
        sessionmaker(bind=migrated_database, autoflush=False)
    )

    result = emit_run(layout, spec, RUN_ID, repository, PSEUDONYMISER)

    assert result.accepted == _grid_size(layout, spec)
    assert _count(migrated_database, "observations") == _grid_size(layout, spec)
    with migrated_database.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT DISTINCT data_mode, observation_type, ST_SRID(location) "
                "FROM observations"
            )
        ).all()

    assert rows == [("synthetic", "rf", 4326)]


@pytest.mark.database
@requires_database
def test_a_run_that_fails_part_way_leaves_no_observations(
    layout: RfLayout, migrated_database: Engine
) -> None:
    """The amendment's third failure case, against a real constraint. The run
    id is absent, so the insert violates the foreign key -- and `scn-003` must
    be able to skip the run knowing the store holds nothing from it."""
    # spec: adp-002, dal-002, scn-003
    repository = PostgisObservationRepository(
        sessionmaker(bind=migrated_database, autoflush=False)
    )

    with pytest.raises(IntegrityError):
        emit_run(layout, _spec(), MISSING_RUN_ID, repository, PSEUDONYMISER)

    assert _count(migrated_database, "observations") == 0
