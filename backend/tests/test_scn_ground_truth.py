"""The answer key reaching the run record. Spec: scn-002 (pass 4 of 4).

`ground_truth` builds the record; this is what puts it where the evaluation can
find it. Two calls rather than one, because the answer key is known in two
instalments:

* **At planning time** the type, the affected receivers, the slices and the
  window are all decided, and they are written with the run row itself.
* **At the end of generation** the affected aircraft are known, because which
  targeted aircraft actually appear inside the zone during the window is a
  property of the corpus rather than of the seed. An answer key naming aircraft
  that never showed up would score the detector as missing things it was never
  shown.

Both instalments happen at *generation* time. Nothing here is ever inferred
from detector output, which is the line `scn-002` draws and the reason a
measurement taken against this record means anything at all.

**It goes on the run row and nowhere else** (`api-009`). `ScenarioRunSummary`
-- what every reader of a run gets -- has no field capable of holding it, so
the answer cannot leak through the API by anyone forgetting to strip it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.dal.models import ScenarioRunSummary
from app.db.migrations import alembic_config
from app.db.repository import create_scenario_run, record_ground_truth
from app.scenario.emitter import BaselineParameters, RunSpec
from app.scenario.incident import (
    IncidentParameters,
    ScenarioType,
    ground_truth,
    plan_incident,
)
from app.scenario.layout import load_layout
from tests.conftest import requires_database

SEED = 20220627
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)


def _spec() -> RunSpec:
    return RunSpec(
        scenario_type=ScenarioType.GNSS_DEGRADATION,
        parameters=BaselineParameters(),
        incident=IncidentParameters(),
        seed=SEED,
        start=START,
        duration_seconds=900,
    )


def _truth() -> dict[str, Any]:
    layout = load_layout()
    spec = _spec()
    return ground_truth(spec, plan_incident(layout, spec))


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", empty_database.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")
    return empty_database


def _stored(engine: Engine, run_id: int) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT ground_truth FROM scenario_runs WHERE id = :id"),
            {"id": run_id},
        ).scalar_one()


# ------------------------------------------------------- the structural half


def test_a_run_summary_cannot_carry_the_answer() -> None:
    # spec: scn-002, api-009
    # The guarantee is the absence of a field, not the discipline of stripping
    # one. A summary with nowhere to put ground truth cannot leak it on any
    # endpoint, present or future.
    assert "ground_truth" not in ScenarioRunSummary.model_fields


# ------------------------------------------------------------ live database


@pytest.mark.database
@requires_database
def test_the_planned_answer_is_written_with_the_run(
    migrated_database: Engine,
) -> None:
    # spec: scn-002
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    truth = _truth()

    run_id = create_scenario_run(
        factory,
        scenario_type="gnss-degradation",
        parameters={},
        seed=SEED,
        ground_truth=truth,
    )

    stored = _stored(migrated_database, run_id)
    assert stored["scenario_type"] == "gnss-degradation"
    assert stored["sensors"] == truth["sensors"]
    assert stored["window"] == truth["window"]


@pytest.mark.database
@requires_database
def test_a_run_with_no_answer_key_stores_null(migrated_database: Engine) -> None:
    # spec: scn-002, db-007
    # A replay stages nothing and has no answer key. Null says so; an empty
    # object would say "staged nothing", which is a different claim and one
    # only the quiet control is entitled to make.
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    run_id = create_scenario_run(
        factory, scenario_type="replay-only", parameters={}, seed=0
    )

    assert _stored(migrated_database, run_id) is None


@pytest.mark.database
@requires_database
def test_the_completed_answer_replaces_the_planned_one(
    migrated_database: Engine,
) -> None:
    # spec: scn-002
    # The second instalment: the aircraft the run actually touched, known only
    # once the corpus has streamed past.
    factory = sessionmaker(bind=migrated_database, autoflush=False)
    run_id = create_scenario_run(
        factory,
        scenario_type="gnss-degradation",
        parameters={},
        seed=SEED,
        ground_truth=_truth(),
    )

    complete = {**_truth(), "aircraft": ["AC-0001", "AC-0002"]}
    record_ground_truth(factory, run_id, complete)

    stored = _stored(migrated_database, run_id)
    assert stored["aircraft"] == ["AC-0001", "AC-0002"]
    assert stored["sensors"] == _truth()["sensors"]


@pytest.mark.database
@requires_database
def test_recording_against_an_unknown_run_is_refused(
    migrated_database: Engine,
) -> None:
    # spec: scn-002, db-007
    # An UPDATE matching nothing is a success by default, so a caller holding
    # the wrong id would record the answer key nowhere and be told it worked --
    # and the run would be scored against an absent ground truth.
    factory = sessionmaker(bind=migrated_database, autoflush=False)

    with pytest.raises(LookupError):
        record_ground_truth(factory, 9999, _truth())
