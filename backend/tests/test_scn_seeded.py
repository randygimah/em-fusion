"""Seeded reproducibility, and the smallest emitter that can prove it.
Spec: scn-001.

`scn-001` is a property rather than a feature -- same type, parameters and
seed give a byte-identical stream -- and a property needs something to hold
over. That something is the baseline RF emitter: one reading per sensor per
channel per interval of `scn-005`'s layout, nominal power plus seeded noise
and nothing injected. Injection is `scn-002`'s and persistence is `adp-002`'s,
so neither appears here.

Four groups, and the third is the reason the file is longer than the property
it tests:

* **The property, in both directions.** Identical inputs give identical
  output, and *different* seeds give different output. The second half is the
  one that is easy to omit and the one that matters: a generator ignoring its
  seed entirely passes the first test perfectly and makes a batch of thirty
  runs thirty copies of one run. The same argument applies to parameters, so
  the parameter arm is asserted too.
* **The seed is always recorded.** A run whose seed was generated rather than
  supplied, and then not written down, can never be repeated -- and the seed
  has to fit `scenario_runs.seed`, which is a 32-bit integer column.
* **The three leaks, each tested in the only way it can be seen.** Wall-clock
  time and unseeded randomness are absences, so they are asserted structurally
  over the package's own syntax tree rather than by observing output that
  happens to match. Process-dependent ordering cannot be seen from inside one
  process at all: it is stable within a process and differs across two, so it
  survives every in-process test ever written. It is tested by emitting in two
  child processes under different `PYTHONHASHSEED` values, with a guard that
  proves the variable actually took effect.
* **The grid, and what a record may not carry.** Every cell present exactly
  once, a deterministic emission order, no provenance (`dal-003` attaches it),
  and no scenario type or ground truth (`api-009`).

The run record moves here from `app/replay.py`, which borrowed it: creating a
run is the generator's job, the seed belongs on the row, and `adp-007` said so
when it wrote the placeholder.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.db.migrations import alembic_config
from app.db.repository import create_scenario_run
from app.scenario.emitter import (
    BaselineParameters,
    RunSpec,
    emit_baseline,
    stream_digest,
)
from app.scenario.layout import RfLayout, load_layout
from app.scenario.seeding import derive_unit, new_seed
from tests.conftest import requires_database

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PACKAGE = BACKEND_ROOT / "app" / "scenario"

#: The run every test in this file emits. Fixed values, because a test that
#: generated its own seed would be testing a different stream each time it ran
#: -- which is the defect the item exists to prevent.
SEED = 20220627
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
DURATION_SECONDS = 60

#: Seven sensors, eight channels, and six ten-second ticks in a minute. Written
#: out rather than computed from the layout, so a layout that quietly loses a
#: sensor is caught here instead of shrinking the expectation with it.
EXPECTED_RECORDS = 7 * 8 * 6

#: `scenario_runs.seed` is `sa.Integer` -- 32-bit and signed. A generated seed
#: that does not fit it fails at insert time, inside `scn-003`'s batch, long
#: after the value was chosen.
SEED_COLUMN_MAX = 2**31 - 1

#: Modules whose presence anywhere in the scenario package is a leak. `random`
#: is unseeded randomness by default, `time` is the wall clock, and `uuid`
#: is both at once. `secrets` is deliberately absent from this list: drawing a
#: seed is the one place entropy is legitimate, because the value it produces
#: becomes a recorded *input* rather than an unrecorded influence on output.
FORBIDDEN_IMPORTS = frozenset({"random", "time", "uuid"})

#: Calls that read a clock or a per-process salt. `hash` is the trap that looks
#: least like one: it is stable within a process and salted across processes,
#: so a stream derived through it is reproducible on every machine that runs
#: the test suite in one go and irreproducible everywhere else.
FORBIDDEN_ATTRIBUTE_CALLS = frozenset(
    {"now", "utcnow", "today", "monotonic", "perf_counter"}
)
FORBIDDEN_NAME_CALLS = frozenset({"hash"})

#: Emitted in a child process, twice, under different hash seeds. Self-contained
#: rather than importing the parent's helper: the two must agree because they
#: describe the same run, not because they share a line of code. `builtin_hash`
#: is the guard -- if the environment variable did not take effect, the two
#: children agree on it, and a matching digest would prove nothing.
CHILD_PROGRAM = """
import json
from datetime import UTC, datetime

from app.scenario.emitter import (
    BaselineParameters,
    RunSpec,
    emit_baseline,
    stream_digest,
)
from app.scenario.layout import load_layout

spec = RunSpec(
    scenario_type="normal-baseline",
    parameters=BaselineParameters(),
    seed=20220627,
    start=datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC),
    duration_seconds=60,
)
print(
    json.dumps(
        {
            "digest": stream_digest(emit_baseline(load_layout(), spec)),
            "builtin_hash": hash("em-fusion"),
        }
    )
)
"""


# ------------------------------------------------------------------- builders


@pytest.fixture()
def layout() -> RfLayout:
    return load_layout()


def _spec(
    *,
    seed: int = SEED,
    parameters: BaselineParameters | None = None,
    duration_seconds: int = DURATION_SECONDS,
) -> RunSpec:
    return RunSpec(
        scenario_type="normal-baseline",
        parameters=parameters if parameters is not None else BaselineParameters(),
        seed=seed,
        start=START,
        duration_seconds=duration_seconds,
    )


def _cells(records: Iterable[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    """The coordinate of each record, without its values.

    Lets a test say "the grid is the same but the numbers are not", which is
    the difference between a seed that changes the readings and one that
    changes which readings exist.
    """
    return [
        (
            record["timestamp"],
            record["payload"]["sensor_id"],
            record["payload"]["channel_index"],
        )
        for record in records
    ]


def _scenario_trees() -> dict[Path, ast.Module]:
    paths = sorted(SCENARIO_PACKAGE.glob("*.py"))
    assert paths, f"no modules found under {SCENARIO_PACKAGE}"
    return {path: ast.parse(path.read_text()) for path in paths}


def _run_child(hash_seed: str) -> dict[str, Any]:
    environment = {
        **os.environ,
        "PYTHONHASHSEED": hash_seed,
        "PYTHONPATH": str(BACKEND_ROOT),
    }
    completed = subprocess.run(
        [sys.executable, "-c", CHILD_PROGRAM],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


# --------------------------------------------------- the property, both halves


def test_identical_inputs_give_an_identical_stream(layout: RfLayout) -> None:
    # spec: scn-001
    first = emit_baseline(layout, _spec())
    second = emit_baseline(layout, _spec())

    assert list(first) == list(second)
    assert stream_digest(first) == stream_digest(second)


def test_a_different_seed_gives_a_different_stream(layout: RfLayout) -> None:
    # spec: scn-001
    # The half that is easy to omit: a generator ignoring its seed is
    # trivially reproducible and controls nothing.
    baseline = emit_baseline(layout, _spec(seed=SEED))
    other = emit_baseline(layout, _spec(seed=SEED + 1))

    assert stream_digest(baseline) != stream_digest(other)
    # The grid is unchanged -- it is the readings that differ, not which cells
    # exist. A seed that changed the shape would be changing the scenario.
    assert _cells(baseline) == _cells(other)


def test_a_different_parameter_gives_a_different_stream(layout: RfLayout) -> None:
    # spec: scn-001
    # A parameter that controls nothing is the same defect as a seed that
    # controls nothing, and is invisible for exactly as long.
    quiet = emit_baseline(
        layout, _spec(parameters=BaselineParameters(noise_sigma_db=0.5))
    )
    loud = emit_baseline(
        layout, _spec(parameters=BaselineParameters(noise_sigma_db=4.0))
    )

    assert stream_digest(quiet) != stream_digest(loud)
    assert _cells(quiet) == _cells(loud)


def test_emitting_twice_from_one_spec_gives_the_same_stream(layout: RfLayout) -> None:
    # spec: scn-001
    # Guards state carried between emissions -- a generator advanced by its
    # first consumer, or a cursor kept on the spec.
    spec = _spec()

    assert stream_digest(emit_baseline(layout, spec)) == stream_digest(
        emit_baseline(layout, spec)
    )


def test_derivation_does_not_depend_on_the_order_cells_are_visited() -> None:
    # spec: scn-001
    # Each cell's value comes from its own coordinates, so visiting the grid
    # backwards, or across workers, cannot change a single reading.
    forward = [
        derive_unit(SEED, "power", sensor, channel)
        for sensor in ("RF-01", "RF-02")
        for channel in range(3)
    ]
    backward = [
        derive_unit(SEED, "power", sensor, channel)
        for sensor in ("RF-02", "RF-01")
        for channel in reversed(range(3))
    ]

    assert sorted(forward) == sorted(backward)
    assert derive_unit(SEED, "power", "RF-01", 0) == forward[0]


# ------------------------------------------------------- the seed is recorded


def test_a_generated_seed_is_recorded_on_the_run(layout: RfLayout) -> None:
    # spec: scn-001
    spec = RunSpec.create(
        scenario_type="normal-baseline",
        start=START,
        duration_seconds=DURATION_SECONDS,
    )

    assert isinstance(spec.seed, int)
    # Written down means reproducible: the recorded value alone must bring the
    # stream back.
    replayed = _spec(seed=spec.seed)
    assert stream_digest(emit_baseline(layout, spec)) == stream_digest(
        emit_baseline(layout, replayed)
    )


def test_a_supplied_seed_is_never_replaced() -> None:
    # spec: scn-001
    spec = RunSpec.create(
        scenario_type="normal-baseline",
        start=START,
        duration_seconds=DURATION_SECONDS,
        seed=SEED,
    )

    assert spec.seed == SEED


def test_a_generated_seed_fits_the_seed_column() -> None:
    # spec: scn-001
    # `scenario_runs.seed` is a 32-bit signed integer. A wider value fails at
    # insert time, inside a batch, long after it was drawn.
    for _ in range(50):
        seed = new_seed()
        assert 0 <= seed <= SEED_COLUMN_MAX


def test_generated_seeds_are_not_a_constant() -> None:
    # spec: scn-001
    # The mirror of the different-seeds arm: a generator handing out one seed
    # forever would make every run in a batch identical.
    assert len({new_seed() for _ in range(20)}) > 1


# ------------------------------------------------------------------ the leaks


def test_the_scenario_package_reads_no_clock_and_no_unseeded_randomness() -> None:
    # spec: scn-001
    # An absence, asserted over the syntax tree rather than the text: db-006
    # showed that a text search fails on the docstring explaining the rule it
    # enforces, and so drives the explanation out of the file.
    offences: list[str] = []

    for path, tree in _scenario_trees().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                        offences.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    offences.append(f"{path.name}: from {node.module} import ...")
            elif isinstance(node, ast.Call):
                function = node.func
                if (
                    isinstance(function, ast.Attribute)
                    and function.attr in FORBIDDEN_ATTRIBUTE_CALLS
                ):
                    offences.append(f"{path.name}: {function.attr}()")
                if (
                    isinstance(function, ast.Name)
                    and function.id in FORBIDDEN_NAME_CALLS
                ):
                    offences.append(f"{path.name}: {function.id}()")

    assert offences == []


def test_a_stream_survives_a_changed_pythonhashseed(layout: RfLayout) -> None:
    # spec: scn-001
    # The leak no in-process test can see. Two children, two hash seeds.
    first = _run_child("0")
    second = _run_child("1")

    # The guard: if the variable did not take effect these agree, and the
    # digest comparison below would prove nothing at all.
    assert first["builtin_hash"] != second["builtin_hash"]

    assert first["digest"] == second["digest"]
    assert first["digest"] == stream_digest(emit_baseline(layout, _spec()))


# ------------------------------------------------- the grid, and what it carries


def test_the_stream_covers_every_cell_exactly_once(layout: RfLayout) -> None:
    # spec: scn-001, scn-005
    records = list(emit_baseline(layout, _spec()))
    cells = _cells(records)

    assert len(records) == EXPECTED_RECORDS
    assert len(set(cells)) == EXPECTED_RECORDS


def test_the_emission_order_is_fixed(layout: RfLayout) -> None:
    # spec: scn-001
    # Derivation is order-independent, but the *stream* is not allowed to be:
    # byte-identity is a claim about a sequence.
    cells = _cells(emit_baseline(layout, _spec()))

    assert cells == sorted(cells)


def test_ticks_step_by_the_layout_interval(layout: RfLayout) -> None:
    # spec: scn-001, scn-005
    stamps = sorted({record["timestamp"] for record in emit_baseline(layout, _spec())})

    assert stamps[0] == START
    assert stamps[-1] == START + timedelta(
        seconds=DURATION_SECONDS - layout.interval_seconds
    )
    steps = {b - a for a, b in zip(stamps, stamps[1:])}
    assert steps == {timedelta(seconds=layout.interval_seconds)}


def test_a_record_carries_no_scenario_type_and_no_ground_truth(
    layout: RfLayout,
) -> None:
    # spec: scn-001, api-009
    record = next(iter(emit_baseline(layout, _spec())))
    keys = set(record) | set(record["payload"])

    assert not {key for key in keys if "scenario" in key or "ground" in key}
    assert "injected" not in keys
    assert "seed" not in keys


def test_a_record_carries_no_provenance(layout: RfLayout) -> None:
    # spec: scn-001, dal-003
    # Provenance is attached at the DAL and never by a source, so a new source
    # cannot forget it -- and cannot claim one either.
    record = next(iter(emit_baseline(layout, _spec())))

    assert "provenance" not in record
    assert "data_mode" not in record
    assert "scenario_run_id" not in record


def test_an_emitted_record_validates_through_the_dal(layout: RfLayout) -> None:
    # spec: scn-001
    # The wiring is adp-002's; that the shape is real rather than plausible is
    # this item's, since a stream nothing can ingest is reproducibly useless.
    from app.dal.models import DataMode, ObservationType
    from app.dal.pseudonymise import Pseudonymiser
    from app.dal.validation import IngestContext, validate_record

    context = IngestContext(data_mode=DataMode.SYNTHETIC, scenario_run_id=1)
    outcome = validate_record(
        next(iter(emit_baseline(layout, _spec()))),
        context,
        Pseudonymiser(seed="a-test-seed-not-the-real-one"),
    )

    assert outcome.rejection is None
    assert outcome.observation is not None
    assert outcome.observation.observation_type is ObservationType.RF


# ------------------------------------------------------------ the run record


def test_replay_holds_no_sql_of_its_own() -> None:
    # spec: scn-001, db-007
    # `adp-007` borrowed the run row and said so. Creating a run is the
    # generator's, and the SQL for it belongs in the storage layer.
    tree = ast.parse((BACKEND_ROOT / "app" / "replay.py").read_text())
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert "sqlalchemy" not in imports
    assert not hasattr(__import__("app.replay", fromlist=["x"]), "create_scenario_run")


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", empty_database.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")
    return empty_database


@pytest.mark.database
@requires_database
def test_create_scenario_run_records_the_seed(migrated_database: Engine) -> None:
    # spec: scn-001
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    run_id = create_scenario_run(
        factory,
        scenario_type="normal-baseline",
        parameters={"noise_sigma_db": 1.5},
        seed=SEED,
    )

    with migrated_database.connect() as connection:
        row = connection.execute(
            text(
                "SELECT scenario_type, parameters, seed, started_at, completed_at "
                "FROM scenario_runs WHERE id = :id"
            ),
            {"id": run_id},
        ).one()

    assert row.scenario_type == "normal-baseline"
    assert row.parameters == {"noise_sigma_db": 1.5}
    assert row.seed == SEED
    assert row.started_at is not None
    # `db-007`: absence is the informative state. A run is not complete because
    # it was created.
    assert row.completed_at is None


@pytest.mark.database
@requires_database
def test_create_scenario_run_gives_each_run_its_own_id(
    migrated_database: Engine,
) -> None:
    # spec: scn-001, scn-003
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    first = create_scenario_run(
        factory, scenario_type="normal-baseline", parameters={}, seed=1
    )
    second = create_scenario_run(
        factory, scenario_type="normal-baseline", parameters={}, seed=2
    )

    assert first != second
