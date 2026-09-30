"""The batch runner's reproducibility, asserted against stored rows. Spec: eval-001.

**Why this file exists when `scn-008` already tests re-derivation.** That item
asserts the property on a constructed `RunSpec`: given a batch, a run knows its
own seed. This asserts it on what was **persisted**, which is a different claim
and the one `eval-001`'s failure case actually makes -- "a batch that cannot be
reproduced from its recorded base seed" is a statement about the record, not
about the function. Between the two lies a JSON round-trip through
`scenario_runs.parameters`, a base seed that comes back as text to be cast, and a
batch index that indexes a list. None of that is exercised by a unit test.

**There is no new production code for this item, and the workflow's prove-red
step is therefore not applicable.** The behaviour was built by `scn-003` and made
recordable by `scn-008`; what was missing was a proof, and the item closes on a
measurement rather than on new behaviour (see its amendment). The substitute for
a red run is the second test below, which feeds the same assertion a row whose
seed does not derive and requires it to fail -- the pattern this repository
already uses wherever a structural check could pass by finding nothing
(`test_the_parser_finds_the_contract_it_claims_to_check` beside
`test_still_catches_a_real_import`). A check that cannot fail is not a check.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.db.repository import create_scenario_run
from app.pipeline import derive_seeds
from app.scenario.emitter import BaselineParameters, RunSpec
from app.scenario.incident import IncidentParameters, ScenarioType
from tests.conftest import requires_database

BASE_SEED = 20260930
BATCH = 20
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)


def _spec(seed: int) -> RunSpec:
    return RunSpec(
        scenario_type=ScenarioType.GNSS_DEGRADATION,
        parameters=BaselineParameters(),
        incident=IncidentParameters(),
        seed=seed,
        start=START,
        duration_seconds=900,
    )


def _stored_runs(factory: sessionmaker) -> list[dict[str, Any]]:
    """Every run row, as a reader with nothing but the database would see it."""
    with factory() as session:
        return [
            dict(row)
            for row in session.execute(
                text("SELECT id, seed, parameters FROM scenario_runs ORDER BY id")
            )
            .mappings()
            .all()
        ]


def _re_derives(row: dict[str, Any]) -> bool | None:
    """Does this row's own record re-derive the seed the row carries?

    `None` means the row records no batch, which is **not** a mismatch: a run
    generated outside a batch records nothing rather than inventing a batch of
    one (`scn-008`), and corpus v1's runs are exactly that. Conflating the two
    would report an older corpus as broken rather than as unprovenanced.
    """
    recorded = row["parameters"]
    if "base_seed" not in recorded:
        return None
    seeds = derive_seeds(int(recorded["base_seed"]), int(recorded["batch_runs"]))
    return seeds[int(recorded["batch_index"])] == row["seed"]


def _write_batch(factory: sessionmaker, *, base_seed: int, runs: int) -> None:
    """A batch written the way `scn-003` writes one."""
    for index, seed in enumerate(derive_seeds(base_seed, runs)):
        spec = _spec(seed).with_batch(base_seed=base_seed, index=index, runs=runs)
        create_scenario_run(
            factory,
            scenario_type=spec.scenario_type.value,
            parameters=spec.as_parameters(),
            seed=spec.seed,
        )


def _seeded(rows: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    """The one row carrying this seed."""
    matching = [row for row in rows if row["seed"] == seed]
    assert len(matching) == 1, f"expected one row with seed {seed}, got {len(matching)}"
    return matching[0]


@requires_database
def test_every_stored_run_re_derives_its_own_seed(migrated_database: Engine) -> None:
    """The item's constraint, against rows rather than against a function.

    Spec: eval-001. Every downstream metric is unverifiable if this fails, which
    is why the item names it as its only failure case.

    Asserted as a property of the **whole table** rather than of the rows this
    test wrote, and deliberately: the shared fixture seeds one run for the bundle
    suites to hang off, which records no batch, so the population here already
    contains an unprovenanced row. That is the realistic shape -- corpus v1's runs
    are exactly that -- and a test that filtered it out would assert a weaker
    property than the one the item states.
    """
    # spec: eval-001, scn-003, scn-008
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _write_batch(factory, base_seed=BASE_SEED, runs=BATCH)

    verdicts = [_re_derives(row) for row in _stored_runs(factory)]

    assert verdicts.count(False) == 0, "a stored run does not re-derive its own seed"
    assert verdicts.count(True) == BATCH


@requires_database
def test_the_check_catches_a_stored_seed_that_does_not_derive(
    migrated_database: Engine,
) -> None:
    """The can-fail proof, standing in for a red run. Spec: eval-001.

    Nothing new was built for this item, so the assertion above passed the moment
    it was written. That is only acceptable if the assertion is capable of
    failing, and this is what establishes it: one row whose recorded batch says
    its seed should be something else.
    """
    # spec: eval-001
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    spec = _spec(derive_seeds(BASE_SEED, BATCH)[0]).with_batch(
        base_seed=BASE_SEED, index=0, runs=BATCH
    )
    create_scenario_run(
        factory,
        scenario_type=spec.scenario_type.value,
        parameters=spec.as_parameters(),
        # The one corruption. Every other column is what the generator wrote.
        seed=spec.seed + 1,
        ground_truth=None,
    )

    rows = _stored_runs(factory)

    assert _re_derives(_seeded(rows, spec.seed + 1)) is False
    # And detected rather than averaged away: one corrupted row is one failure.
    assert [_re_derives(row) for row in rows].count(False) == 1


@requires_database
def test_a_run_recording_no_batch_is_unprovenanced_rather_than_wrong(
    migrated_database: Engine,
) -> None:
    """Spec: eval-001, scn-008.

    A run generated outside a batch records no batch, and reading that as a
    mismatch would report corpus v1 -- whose runs predate `scn-008` entirely --
    as a reproducibility failure rather than as a corpus nothing can check.
    """
    # spec: eval-001, scn-008
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    spec = _spec(BASE_SEED)
    create_scenario_run(
        factory,
        scenario_type=spec.scenario_type.value,
        parameters=spec.as_parameters(),
        seed=spec.seed,
    )

    unbatched = _seeded(_stored_runs(factory), spec.seed)

    assert "base_seed" not in unbatched["parameters"]
    assert _re_derives(unbatched) is None
