"""The third source: a synthetic receiver health feed. Spec: adp-003.

The extensibility measurement (RQ1). The feed is deliberately small -- each
receiver reports its temperature, supply voltage and uptime once a minute -- so
that what is measured is the cost of adding a source, not of the source itself.
These tests hold the spec's constraints:

* **Shape**: a generator in `app/scenario/` and a driver in `app/adapters/`,
  as `adp-002` is built, the driver inventing nothing and creating no run.
* **Blind to the incident**: the generator is never told what a run stages.
* **Registration only**: the DAL accepts the new type with nothing changed but
  `models.py`; the store takes it with no migration.
* **Nothing changes downstream**: the detection pass and the operational
  picture are identical with and without the feed on the same run.
* **Not wired in**: no module of the app imports either new module.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.adapters import receiver_health as driver
from app.adapters.receiver_health import emit_run
from app.dal.models import (
    PAYLOAD_TYPES,
    CanonicalObservation,
    DataMode,
    Location,
    ObservationType,
    Provenance,
    ReceiverHealthPayload,
    RfPayload,
    SourceType,
    ValidationStatus,
)
from app.dal.pseudonymise import IDENTIFIER_RULES, Pseudonymiser
from app.db.repository import PostgisObservationRepository
from app.detection.chain import assess_without_storing
from app.scenario import receiver_health as generator
from app.scenario.emitter import BaselineParameters, RunSpec, stream_digest
from app.scenario.incident import IncidentParameters, ScenarioType
from app.scenario.layout import RfLayout, load_layout
from app.scenario.receiver_health import INTERVAL_SECONDS, emit_health
from tests.conftest import requires_database
from tests.fakes import FailingObservationRepository, InMemoryObservationRepository
from tests.test_api_operational_picture import (
    HOUR_START,
    _get,
    _insert_run,
    _observation,
    _reading,
    _save,
    picture_database,  # noqa: F401 -- the fixture, shared rather than copied
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]

SEED = 20220627
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
#: Five minutes: five reports per receiver.
DURATION_SECONDS = 300
RUN_ID = 1

PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")
OTHER_PSEUDONYMISER = Pseudonymiser(seed="a-different-test-seed")

PAYLOAD_FIELDS = {"sensor_id", "temperature_c", "supply_voltage_v", "uptime_s"}


@pytest.fixture()
def layout() -> RfLayout:
    return load_layout()


def _feed(layout: RfLayout, *, seed: int = SEED) -> tuple[dict[str, Any], ...]:
    return emit_health(layout, seed, START, DURATION_SECONDS)


def _run(
    layout: RfLayout,
    repository: InMemoryObservationRepository,
    *,
    seed: int = SEED,
    pseudonymiser: Pseudonymiser = PSEUDONYMISER,
) -> Any:
    return emit_run(
        layout,
        seed=seed,
        start=START,
        duration_seconds=DURATION_SECONDS,
        scenario_run_id=RUN_ID,
        repository=repository,
        pseudonymiser=pseudonymiser,
    )


def _digest(observations: Sequence[CanonicalObservation]) -> str:
    return stream_digest(
        [
            {
                "timestamp": o.timestamp,
                **o.location.model_dump(),
                **o.payload.model_dump(),
            }
            for o in observations
        ]
    )


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


# ------------------------------------------------------------- the generator


def test_every_receiver_reports_once_a_minute(layout: RfLayout) -> None:
    # spec: adp-003 -- one report per layout receiver every 60 s, half-open on
    # the duration like `scn-001`'s ticks
    feed = _feed(layout)

    cells = [(r["timestamp"], r["payload"]["sensor_id"]) for r in feed]
    expected = {
        (START + timedelta(seconds=step * INTERVAL_SECONDS), site.sensor_id)
        for step in range(DURATION_SECONDS // INTERVAL_SECONDS)
        for site in layout.sensors
    }
    assert INTERVAL_SECONDS == 60
    assert len(cells) == len(expected)
    assert set(cells) == expected


def test_each_report_sits_at_its_receiver_and_carries_four_fields(
    layout: RfLayout,
) -> None:
    # spec: adp-003
    positions = {site.sensor_id: (site.lat, site.lon) for site in layout.sensors}

    for record in _feed(layout):
        assert record["source_type"] is SourceType.SYNTHETIC_HEALTH
        assert record["observation_type"] is ObservationType.RECEIVER_HEALTH
        assert set(record["payload"]) == PAYLOAD_FIELDS
        site = record["payload"]["sensor_id"]
        assert (record["location"]["lat"], record["location"]["lon"]) == positions[site]


def test_uptime_advances_with_simulated_time_and_the_supply_is_live(
    layout: RfLayout,
) -> None:
    # spec: adp-003 -- a receiver's uptime grows by exactly the time between its
    # reports; nothing in the feed restarts a receiver
    by_sensor: dict[str, list[dict[str, Any]]] = {}
    for record in _feed(layout):
        by_sensor.setdefault(record["payload"]["sensor_id"], []).append(record)

    for reports in by_sensor.values():
        uptimes = [r["payload"]["uptime_s"] for r in reports]
        assert uptimes[0] >= 0
        assert all(b - a == INTERVAL_SECONDS for a, b in zip(uptimes, uptimes[1:]))
        assert all(r["payload"]["supply_voltage_v"] > 0 for r in reports)


def test_the_same_seed_gives_the_same_feed_and_another_does_not(
    layout: RfLayout,
) -> None:
    # spec: adp-003 (1), scn-001
    assert stream_digest(_feed(layout)) == stream_digest(_feed(layout))
    assert stream_digest(_feed(layout)) != stream_digest(_feed(layout, seed=SEED + 1))


def test_receivers_do_not_all_read_alike(layout: RfLayout) -> None:
    # spec: adp-003 (1) -- the trap arm: a feed of one constant is deterministic
    # and useless
    temperatures = {r["payload"]["temperature_c"] for r in _feed(layout)}
    voltages = {r["payload"]["supply_voltage_v"] for r in _feed(layout)}

    assert len(temperatures) > 1
    assert len(voltages) > 1


def test_the_generator_is_never_told_what_was_staged() -> None:
    # spec: adp-003 (2), api-009 -- blind by its signature, not by care
    assert list(inspect.signature(emit_health).parameters) == [
        "layout",
        "seed",
        "start",
        "duration_seconds",
    ]
    imported = _imports(generator)
    assert "app.scenario.incident" not in imported
    assert "app.scenario.emitter.RunSpec" not in imported


def test_two_runs_differing_only_in_staging_store_the_same_feed(
    layout: RfLayout,
) -> None:
    # spec: adp-003 (2) failure case
    def spec(scenario_type: ScenarioType, offset: int) -> RunSpec:
        return RunSpec(
            scenario_type=scenario_type,
            parameters=BaselineParameters(),
            incident=IncidentParameters(start_offset_s=offset, duration_s=30),
            seed=SEED,
            start=START,
            duration_seconds=DURATION_SECONDS,
        )

    stored = []
    for run in (
        spec(ScenarioType.GNSS_DEGRADATION, 10),
        spec(ScenarioType.NORMAL_BASELINE, 120),
    ):
        repository = InMemoryObservationRepository()
        emit_run(
            layout,
            seed=run.seed,
            start=run.start,
            duration_seconds=run.duration_seconds,
            scenario_run_id=RUN_ID,
            repository=repository,
            pseudonymiser=PSEUDONYMISER,
        )
        stored.append(_digest(repository.observations))

    assert stored[0] == stored[1]


# ----------------------------------------------------------- registration


def test_the_dal_knows_the_new_type() -> None:
    # spec: adp-003 (3) -- registration in models.py, and only there
    assert SourceType.SYNTHETIC_HEALTH.value == "synthetic_health"
    assert ObservationType.RECEIVER_HEALTH.value == "receiver_health"
    assert PAYLOAD_TYPES[ObservationType.RECEIVER_HEALTH] is ReceiverHealthPayload
    assert set(ReceiverHealthPayload.model_fields) == PAYLOAD_FIELDS


def test_pseudonymisation_needs_no_entry_for_it() -> None:
    # spec: adp-003 (3), dal-004 -- a receiver id is not a person's identity
    assert ObservationType.RECEIVER_HEALTH not in IDENTIFIER_RULES


def test_a_health_report_cannot_carry_another_source_payload() -> None:
    # spec: adp-003 (3), dal-001 -- the existing type check covers the new type
    with pytest.raises(ValidationError):
        CanonicalObservation(
            source_id="synthetic-health",
            source_type=SourceType.SYNTHETIC_HEALTH,
            observation_type=ObservationType.RECEIVER_HEALTH,
            timestamp=START,
            location=Location(lat=51.5, lon=5.7),
            data_mode=DataMode.SYNTHETIC,
            validation_status=ValidationStatus.VALID,
            provenance=Provenance(
                source_id="synthetic-health",
                source_type=SourceType.SYNTHETIC_HEALTH,
                data_mode=DataMode.SYNTHETIC,
                scenario_run_id=RUN_ID,
            ),
            payload=RfPayload(
                sensor_id="RF-01",
                channel_index=0,
                centre_frequency_mhz=1575.42,
                band="L1",
                power_dbm=-95.0,
                snr_db=20.0,
                bandwidth_mhz=2.0,
                signal_type="noise",
                baseline_delta_db=0.0,
            ),
        )


# ----------------------------------------------------------------- the driver


def test_the_feed_reaches_the_store_unaltered(layout: RfLayout) -> None:
    # spec: adp-003 (1) -- through ingest_batch, nothing quarantined or changed
    repository = InMemoryObservationRepository()
    feed = _feed(layout)

    result = _run(layout, repository)

    assert result.accepted == len(feed)
    assert result.quarantined == 0
    for observation, record in zip(repository.observations, feed, strict=True):
        assert observation.timestamp == record["timestamp"]
        assert observation.location.model_dump() == record["location"]
        assert observation.payload.model_dump() == record["payload"]
        assert isinstance(observation.payload, ReceiverHealthPayload)


def test_every_report_is_synthetic_and_belongs_to_its_run(layout: RfLayout) -> None:
    # spec: adp-003 (1), op-001, dal-003
    repository = InMemoryObservationRepository()
    _run(layout, repository)

    assert {o.data_mode for o in repository.observations} == {DataMode.SYNTHETIC}
    assert {o.provenance.scenario_run_id for o in repository.observations} == {RUN_ID}


def test_the_driver_cannot_mark_a_feed_replayed() -> None:
    # spec: adp-003 (1) -- the data mode is fixed, not an argument
    tree = ast.parse(Path(driver.__file__).read_text(encoding="utf-8"))
    referenced = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}

    assert "SYNTHETIC" in referenced
    assert "REPLAYED" not in referenced
    assert "data_mode" not in inspect.signature(emit_run).parameters


def test_the_pseudonym_seed_changes_nothing(layout: RfLayout) -> None:
    # spec: adp-003 (3), dal-004
    first = InMemoryObservationRepository()
    second = InMemoryObservationRepository()

    _run(layout, first)
    _run(layout, second, pseudonymiser=OTHER_PSEUDONYMISER)

    assert _digest(first.observations) == _digest(second.observations)


def test_one_run_is_one_batch_and_a_failed_write_is_reported(
    layout: RfLayout,
) -> None:
    # spec: adp-003 (1), dal-002
    repository = InMemoryObservationRepository()
    _run(layout, repository)
    assert repository.calls == 1

    failing = FailingObservationRepository()
    with pytest.raises(RuntimeError, match="not having it"):
        _run(layout, failing)
    assert failing.observations == []


def test_the_driver_invents_nothing_and_opens_no_run() -> None:
    # spec: adp-003 (1), db-007
    imported = _imports(driver)
    defined = {
        n.name
        for n in ast.walk(ast.parse(Path(driver.__file__).read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef)
    }

    assert not {"random", "secrets", "hashlib"} & imported
    assert not [name for name in imported if name.startswith("app.scenario.seeding")]
    assert "sqlalchemy" not in {name.split(".")[0] for name in imported}
    for name in ("create_scenario_run", "record_ground_truth", "complete_scenario_run"):
        assert name not in defined


def test_nothing_in_the_app_wires_the_feed_in() -> None:
    # spec: adp-003 (5) -- tests only: no batch, pipeline or reader imports it
    new = {Path(generator.__file__).resolve(), Path(driver.__file__).resolve()}
    wired = []
    for path in (BACKEND_ROOT / "app").rglob("*.py"):
        if path.resolve() in new:
            continue
        source = path.read_text(encoding="utf-8")
        if "receiver_health" in source or "RECEIVER_HEALTH" in source:
            wired.append(path.relative_to(BACKEND_ROOT).as_posix())

    assert wired == ["app/dal/models.py"]


# ------------------------------------------------------------- live database


@pytest.mark.database
@requires_database
def test_the_store_takes_the_feed_with_no_migration(
    layout: RfLayout, factory: sessionmaker, migrated_database: Engine
) -> None:
    # spec: adp-003 (3) -- the schema at head, untouched, holds the new type
    from tests.conftest import RUN_ID as STORED_RUN

    result = emit_run(
        layout,
        seed=SEED,
        start=START,
        duration_seconds=DURATION_SECONDS,
        scenario_run_id=STORED_RUN,
        repository=PostgisObservationRepository(factory),
        pseudonymiser=PSEUDONYMISER,
    )

    with migrated_database.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT DISTINCT data_mode, source_type, observation_type, "
                "ST_SRID(location) FROM observations"
            )
        ).all()
        count = connection.execute(
            text("SELECT count(*) FROM observations")
        ).scalar_one()

    assert rows == [("synthetic", "synthetic_health", "receiver_health", 4326)]
    assert count == result.accepted == len(_feed(layout))


@pytest.mark.database
@requires_database
def test_the_detection_pass_is_identical_with_the_feed(
    migrated_database: Engine,
) -> None:
    # spec: adp-003 (4) failure case -- any change to a run's pass
    from tests.test_anom_chain import LAYOUT, POLICIES, _normality, _store
    from tests.test_anom_chain import START as CHAIN_START
    from tests.test_anom_chain import _run as run_of
    from tests.test_evb_persisted import LOUD
    from tests.test_evb_persisted import RUN_ID as CHAIN_RUN

    factory = sessionmaker(bind=migrated_database, autoflush=False)
    _store(factory, CHAIN_RUN, elevate=LOUD)

    def measure() -> Any:
        return assess_without_storing(
            run_of(),
            normality=_normality(),
            policies=POLICIES,
            layout=LAYOUT,
            engine=migrated_database,
        )

    without = measure()
    emit_run(
        LAYOUT,
        seed=SEED,
        start=CHAIN_START,
        duration_seconds=600,
        scenario_run_id=CHAIN_RUN,
        repository=PostgisObservationRepository(factory),
        pseudonymiser=PSEUDONYMISER,
    )
    with_feed = measure()

    assert without.reported
    assert with_feed.reported == without.reported
    assert with_feed.bundles == without.bundles


@pytest.mark.database
@requires_database
def test_the_operational_picture_is_identical_with_the_feed(
    picture_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: adp-003 (4) failure case -- any change to the picture; api-020 is
    # the defect this guards against recurring for a third source
    _insert_run(picture_database, RUN_ID, completed=True)
    _save(
        picture_database,
        [
            _observation(aircraft_id="AC-a", offset_s=3600),
            _observation(aircraft_id="AC-b", offset_s=3590),
            _reading(offset_s=3595),
        ],
    )
    without = _get(picture_database, monkeypatch)

    emit_run(
        load_layout(),
        seed=SEED,
        start=HOUR_START,
        duration_seconds=3660,
        scenario_run_id=RUN_ID,
        repository=PostgisObservationRepository(
            sessionmaker(bind=picture_database, autoflush=False)
        ),
        pseudonymiser=PSEUDONYMISER,
    )
    with_feed = _get(picture_database, monkeypatch)

    assert without["aircraftTracks"]
    assert with_feed == without
