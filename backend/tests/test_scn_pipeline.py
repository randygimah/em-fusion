"""Batch execution: the executor and the command. Spec: scn-003 (pass 2 of 2).

Pass 1 derived the seeds and the windows. This is what a batch does with them.

**Both halves, every run.** A run is the synthetic radio grid *and* a window of
the replayed corpus, whichever type it is. The two that stage nothing on the
track side need the stream present for the same reason the quiet control does:
the fusion rule and the data-source rule are defined across both sources, so in
a run holding no track observations their silence is a property of what the run
omitted rather than of what they concluded.

**Mostly database-tier, on purpose.** A run is a row plus the observations
written under it, so proving it against an in-memory fake would prove something
weaker than the claim. The unit tier here covers the paths that must fail
*before* any of that happens, and the structural assertions that close
`ops-003`'s carve-out for `make generate`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.adapters.opensky import Window
from app.corpus.extract import write_parquet
from app.dal.pseudonymise import SEED_ENV_VAR, Pseudonymiser
from app.db.migrations import alembic_config
from app.db.repository import PostgisObservationRepository
from app.pipeline import (
    MIN_RUNS,
    RunOutcome,
    execute_run,
    main,
    run_batch,
)
from app.scenario.emitter import BaselineParameters, RunSpec
from app.scenario.incident import IncidentParameters, ScenarioType, centre_sensor_id
from app.scenario.layout import RfLayout, load_layout
from app.scenario.tracks import TrackPerturber, plan_track_perturbation
from tests.conftest import requires_database
from tests.fakes import FailingObservationRepository

BASE_SEED = 20220627

#: A ten-minute fixture corpus at the real ten-second cadence. Long enough that
#: twenty sixty-second runs each get their own window inside it.
CORPUS_START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
CORPUS = Window(start=CORPUS_START, end=CORPUS_START + timedelta(seconds=600))
EPOCH_START = int(CORPUS_START.timestamp())
RUN_SECONDS = 60

PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")

COMPOSE_PATHS = (
    Path(__file__).resolve().parents[2] / "compose.yaml",
    Path("/repo/compose.yaml"),
)
MAKEFILE_PATHS = (
    Path(__file__).resolve().parents[2] / "Makefile",
    Path("/repo/Makefile"),
)


# ------------------------------------------------------------------- helpers


def _uncommented(text_of: str) -> str:
    """The lines that are recipe or configuration rather than commentary.

    The first version of the assertion below searched the whole Makefile for
    the module name and passed against a *comment* saying the pipeline service
    names a module that does not exist -- the exact defect `docs/qa.md` §38
    records and `test_replay.py` already guards against. A text search cannot
    tell a rule from a description of one.
    """
    return "\n".join(
        line for line in text_of.splitlines() if not line.strip().startswith("#")
    )


def _read(candidates: Sequence[Path]) -> str:
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise AssertionError(  # pragma: no cover -- a broken checkout or mount
        f"not found at any of {[str(p) for p in candidates]}. Skipping is "
        "deliberately not an option here: see `test_replay.py`."
    )


def _spec(
    *,
    scenario_type: ScenarioType = ScenarioType.AIRCRAFT_COVERAGE_GAP,
    seed: int = BASE_SEED,
    start: datetime | None = None,
) -> RunSpec:
    return RunSpec(
        scenario_type=scenario_type,
        parameters=BaselineParameters(),
        # The whole fixture run is inside the staged window, so a suppression
        # has somewhere to happen in sixty seconds of corpus.
        incident=IncidentParameters(start_offset_s=10, duration_s=40),
        seed=seed,
        start=start if start is not None else CORPUS_START,
        duration_seconds=RUN_SECONDS,
    )


def _targeted_identifiers(layout: RfLayout, spec: RunSpec, wanted: int) -> list[str]:
    """Source addresses this run's perturber actually stages on.

    Selection is a keyed draw over the pseudonym at an eight per cent rate, so
    a fixture of arbitrary aircraft would stage nothing most of the time and
    the test would pass or fail on which addresses were typed. Precedent:
    `test_scn_ambiguous.py` does the same thing for one identifier.
    """
    perturbation = plan_track_perturbation(layout, spec)
    assert perturbation is not None
    perturber = TrackPerturber(perturbation, pseudonymiser=PSEUDONYMISER)

    found: list[str] = []
    for value in range(0x100000, 0x400000):
        candidate = f"{value:06x}"
        if perturber.targets(candidate):
            found.append(candidate)
            if len(found) == wanted:
                return found
    raise AssertionError(  # pragma: no cover -- 8% of a 3M range
        f"no {wanted} targeted identifiers found"
    )


def _row(icao24: str, offset_s: int, lat: float, lon: float) -> dict[str, str]:
    """One extract row as CSV cells, the shape `write_parquet` coerces."""
    return {
        "time": str(EPOCH_START + offset_s),
        "icao24": icao24,
        "lat": f"{lat}",
        "lon": f"{lon}",
        "velocity": "194.26",
        "heading": "135.64",
        "vertrate": "13.32",
        "callsign": "TEST123 ",
        "onground": "false",
        "alert": "false",
        "spi": "false",
        "squawk": "1000",
        "baroaltitude": "5753.1",
        "geoaltitude": "5951.22",
        "lastposupdate": str(EPOCH_START + offset_s - 2),
        "lastcontact": str(EPOCH_START + offset_s - 1),
    }


@pytest.fixture()
def layout() -> RfLayout:
    return load_layout()


@pytest.fixture()
def extract(tmp_path: Path, layout: RfLayout) -> Path:
    """A corpus whose aircraft sit at the zone centre this seed picks.

    Placed there deliberately: the perturber only touches aircraft inside the
    staged zone, so a fixture scattered at random would test the geometry
    rather than the staging.
    """
    centre = layout.site(centre_sensor_id(layout, BASE_SEED))
    identifiers = _targeted_identifiers(layout, _spec(), 3)
    # One untargeted aircraft, so a run that suppressed everything would be
    # visible as a run that suppressed everything.
    identifiers.append("000001")

    rows = [
        _row(icao24, offset, centre.lat, centre.lon)
        for icao24 in identifiers
        for offset in range(0, 600, 10)
    ]
    path = tmp_path / "opensky_extract.parquet"
    write_parquet(rows, path)
    return path


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", empty_database.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")
    return empty_database


@pytest.fixture
def factory(migrated_database: Engine) -> sessionmaker:
    return sessionmaker(bind=migrated_database, autoflush=False)


def _count(engine: Engine, table: str, where: str = "TRUE") -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE {where}")
            ).scalar_one()
        )


def _run_rows(engine: Engine) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT id, scenario_type, seed, parameters, ground_truth, "
                    "completed_at FROM scenario_runs ORDER BY id"
                )
            ).all()
        )


def _execute(
    layout: RfLayout,
    spec: RunSpec,
    extract: Path,
    factory: sessionmaker,
    repository: Any = None,
) -> RunOutcome:
    return execute_run(
        layout,
        spec,
        extract=extract,
        repository=(
            PostgisObservationRepository(factory) if repository is None else repository
        ),
        pseudonymiser=PSEUDONYMISER,
        session_factory=factory,
    )


# ------------------------------------------------------- one run, both halves


@pytest.mark.database
@requires_database
def test_a_run_stores_both_halves(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    # spec: scn-003, adp-002, adp-001
    outcome = _execute(layout, _spec(), extract, factory)

    assert outcome.completed
    assert outcome.rf_accepted > 0
    assert outcome.track_accepted > 0
    assert _count(migrated_database, "observations", "observation_type = 'rf'") > 0
    assert _count(migrated_database, "observations", "observation_type = 'track'") > 0


@pytest.mark.database
@requires_database
def test_the_quiet_control_carries_tracks_too(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """The failure case this decision exists for. A control holding no track
    observations measures the false-positive rate of the radio half alone,
    while the write-up would quote it for the system."""
    # spec: scn-003, anom-008
    outcome = _execute(
        layout, _spec(scenario_type=ScenarioType.NORMAL_BASELINE), extract, factory
    )

    assert outcome.completed
    assert _count(migrated_database, "observations", "observation_type = 'track'") > 0
    assert outcome.aircraft_staged == 0


@pytest.mark.database
@requires_database
def test_the_sensor_fault_run_carries_tracks_it_does_not_stage_on(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """A faulty receiver says nothing about the aircraft it happens to be
    listening to -- but the fusion rule fires on RF deviation *plus* co-located
    track trouble, so it has to be shown tracks in order to stay silent for the
    right reason."""
    # spec: scn-003, anom-005
    outcome = _execute(
        layout, _spec(scenario_type=ScenarioType.RF_SENSOR_FAULT), extract, factory
    )

    assert outcome.completed
    assert _count(migrated_database, "observations", "observation_type = 'track'") > 0
    assert outcome.aircraft_staged == 0


@pytest.mark.database
@requires_database
def test_a_coverage_gap_run_withholds_the_rows_it_stages(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    # spec: scn-003, scn-002
    quiet = _execute(
        layout, _spec(scenario_type=ScenarioType.NORMAL_BASELINE), extract, factory
    )
    staged = _execute(
        layout,
        _spec(scenario_type=ScenarioType.AIRCRAFT_COVERAGE_GAP),
        extract,
        factory,
    )

    assert staged.track_accepted < quiet.track_accepted
    assert staged.aircraft_staged > 0


@pytest.mark.database
@requires_database
def test_the_answer_key_names_the_aircraft_actually_staged(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """Collected while the corpus streams past, not predicted from the seed:
    whether a targeted aircraft appears inside the zone during the window is a
    property of the data."""
    # spec: scn-003, scn-002
    outcome = _execute(layout, _spec(), extract, factory)

    (row,) = _run_rows(migrated_database)
    assert row.ground_truth["aircraft"]
    assert len(row.ground_truth["aircraft"]) == outcome.aircraft_staged
    # Pseudonyms, never source addresses (`dal-004`).
    assert all(name.startswith("AC-") for name in row.ground_truth["aircraft"])


@pytest.mark.database
@requires_database
def test_the_run_row_records_its_window_and_is_marked_complete(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    # spec: scn-003, db-007
    spec = _spec(start=CORPUS_START + timedelta(seconds=120))
    _execute(layout, spec, extract, factory)

    (row,) = _run_rows(migrated_database)
    assert row.parameters["start"] == spec.start.isoformat()
    assert row.parameters["duration_seconds"] == RUN_SECONDS
    assert row.completed_at is not None
    assert (
        RunSpec.from_record(
            scenario_type=row.scenario_type, parameters=row.parameters, seed=row.seed
        )
        == spec
    )


# ------------------------------------------------- a failing run is recorded


@pytest.mark.database
@requires_database
def test_a_failing_run_is_recorded_and_left_incomplete(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """`db-007`: absence is the informative state. Nothing is deleted, and the
    run does not claim to have finished."""
    # spec: scn-003, db-007
    outcome = _execute(
        layout, _spec(), extract, factory, repository=FailingObservationRepository()
    )

    assert not outcome.completed
    assert outcome.error
    (row,) = _run_rows(migrated_database)
    assert row.completed_at is None


@pytest.mark.database
@requires_database
def test_one_failing_run_does_not_abort_the_batch(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """The item's own first failure case. The repository refuses the fourth
    write, so one run fails in the middle rather than at the end."""
    # spec: scn-003

    class RefusesOneRun(PostgisObservationRepository):
        def __init__(self, session_factory: sessionmaker) -> None:
            super().__init__(session_factory)
            self.calls = 0

        def save_batch(self, observations: Any, quarantined: Any) -> None:
            self.calls += 1
            if self.calls == 4:
                raise RuntimeError("the database is not having this one")
            super().save_batch(observations, quarantined)

    summary = run_batch(
        layout,
        scenario_type=ScenarioType.AIRCRAFT_COVERAGE_GAP,
        base_seed=BASE_SEED,
        count=MIN_RUNS,
        corpus=CORPUS,
        duration_seconds=RUN_SECONDS,
        extract=extract,
        repository=RefusesOneRun(factory),
        pseudonymiser=PSEUDONYMISER,
        session_factory=factory,
        incident=IncidentParameters(start_offset_s=10, duration_s=40),
    )

    assert len(summary.runs) == MIN_RUNS
    assert summary.failed == 1
    assert summary.completed == MIN_RUNS - 1
    assert _count(migrated_database, "scenario_runs", "completed_at IS NULL") == 1


# ------------------------------------------------------------- the whole batch


@pytest.mark.database
@requires_database
def test_a_batch_gives_every_run_its_own_seed_and_window(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    # spec: scn-003
    summary = run_batch(
        layout,
        scenario_type=ScenarioType.GNSS_DEGRADATION,
        base_seed=BASE_SEED,
        count=MIN_RUNS,
        corpus=CORPUS,
        duration_seconds=RUN_SECONDS,
        extract=extract,
        repository=PostgisObservationRepository(factory),
        pseudonymiser=PSEUDONYMISER,
        session_factory=factory,
        incident=IncidentParameters(start_offset_s=10, duration_s=40),
    )

    rows = _run_rows(migrated_database)
    assert len(rows) == MIN_RUNS
    assert len({row.seed for row in rows}) == MIN_RUNS
    assert len({row.parameters["start"] for row in rows}) == MIN_RUNS
    assert summary.completed == MIN_RUNS
    assert all(row.ground_truth is not None for row in rows)


@pytest.mark.database
@requires_database
def test_the_report_carries_a_staged_aircraft_count_per_run(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """Detectability varies with this number and the variation sits inside a
    batch, so an aggregate that hides it averages a nearly undetectable run
    with an easy one."""
    # spec: scn-003, eval-001
    summary = run_batch(
        layout,
        scenario_type=ScenarioType.AIRCRAFT_COVERAGE_GAP,
        base_seed=BASE_SEED,
        count=MIN_RUNS,
        corpus=CORPUS,
        duration_seconds=RUN_SECONDS,
        extract=extract,
        repository=PostgisObservationRepository(factory),
        pseudonymiser=PSEUDONYMISER,
        session_factory=factory,
        incident=IncidentParameters(start_offset_s=10, duration_s=40),
    )

    assert all(isinstance(run.aircraft_staged, int) for run in summary.runs)
    assert "aircraft" in summary.render()
    assert str(summary.runs[0].seed) in summary.render()


# --------------------------------------------- it fails before it writes


def test_a_missing_corpus_exits_before_touching_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`adp-007`'s rule: a misconfigured invocation leaves no orphan run.

    The seed is supplied so that this test fails on the corpus rather than on
    the seed check ahead of it -- two tests asserting different messages about
    the same empty directory have to differ in what they leave out.
    """
    # spec: scn-003, adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")

    code = main(
        [
            "--scenario-type",
            "gnss-degradation",
            "--base-seed",
            str(BASE_SEED),
            "--runs",
            str(MIN_RUNS),
            "--data-dir",
            str(tmp_path),
        ],
        env_file=None,
    )

    assert code == 2
    assert "manifest" in capsys.readouterr().err


def test_a_run_count_outside_the_range_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # spec: scn-003
    code = main(
        [
            "--scenario-type",
            "gnss-degradation",
            "--base-seed",
            str(BASE_SEED),
            "--runs",
            "5",
            "--data-dir",
            str(tmp_path),
        ],
        env_file=None,
    )

    assert code == 2
    assert "between" in capsys.readouterr().err


def test_an_unknown_scenario_type_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # spec: scn-003
    code = main(
        [
            "--scenario-type",
            "broadband-interference",
            "--base-seed",
            str(BASE_SEED),
            "--runs",
            str(MIN_RUNS),
            "--data-dir",
            str(tmp_path),
        ],
        env_file=None,
    )

    assert code == 2
    assert "broadband-interference" in capsys.readouterr().err


def test_a_missing_pseudonym_seed_exits_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without it the whole corpus pseudonymises under an empty seed, and the
    identifiers cannot be reconciled with any other run (`dal-004`)."""
    # spec: scn-003, dal-004
    monkeypatch.delenv(SEED_ENV_VAR, raising=False)

    code = main(
        [
            "--scenario-type",
            "gnss-degradation",
            "--base-seed",
            str(BASE_SEED),
            "--runs",
            str(MIN_RUNS),
            "--data-dir",
            str(tmp_path),
        ],
        env_file=None,
    )

    assert code == 2
    assert SEED_ENV_VAR in capsys.readouterr().err


# ------------------------------------------------ the command surface agrees


def test_compose_and_make_generate_name_this_module() -> None:
    """`ops-003` carried `make generate` as knowingly broken because the
    pipeline service named a module that did not exist. This is the assertion
    that lifts the carve-out, and it fails again the moment either side is
    renamed without the other."""
    # spec: scn-003, ops-003
    compose = _uncommented(_read(COMPOSE_PATHS))
    makefile = _uncommented(_read(MAKEFILE_PATHS))

    assert "app.pipeline" in compose
    assert "app.pipeline" in makefile
    assert (Path(__file__).resolve().parents[1] / "app" / "pipeline.py").is_file()


def test_make_generate_passes_a_type_a_base_seed_and_a_run_count() -> None:
    """A batch target that defaulted to nothing would produce an unreproducible
    campaign on a fresh machine, which is the failure `scn-001` exists to
    prevent one level down."""
    # spec: scn-003, ops-003
    text_of = _uncommented(_read(MAKEFILE_PATHS))

    assert "PIPELINE_ARGS" in text_of
    for flag in ("--scenario-type", "--base-seed", "--runs"):
        assert flag in text_of
