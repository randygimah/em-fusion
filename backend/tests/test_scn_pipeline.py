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

import io
import json
import shutil
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
from tests.conftest import live_database_url, requires_database
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


class _RefusesToOpenRuns:
    """A session factory that will not open a run. Used where a test needs to
    reach the batch loop without a database."""

    def begin(self) -> Any:
        raise RuntimeError("no runs today")


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
    # The two halves are marked differently, and deliberately. A perturbed row
    # is a real recorded observation a scenario edited, not one the generator
    # invented, and `data_mode` describes where an observation came from. What
    # makes the run synthetic is on the run record, where a detector cannot see
    # it -- so `op-001`'s badge has to key off the run, not off a track row.
    assert _count(
        migrated_database, "observations", "observation_type = 'rf'"
    ) == _count(migrated_database, "observations", "data_mode = 'synthetic'")
    assert _count(
        migrated_database, "observations", "observation_type = 'track'"
    ) == _count(migrated_database, "observations", "data_mode = 'replayed'")


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
    # Observed on the first real batch: one run in twenty staged nothing at
    # all, because where the seed put the zone decided how much traffic was in
    # it. A summary that hid that would let a campaign quote recall over runs
    # that contained no incident.
    assert summary.staged_nothing == sum(
        1 for run in summary.runs if run.completed and not run.aircraft_staged
    )
    assert "staged none" in summary.render()


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


def _invoke(data_dir: Path, env_file: Path | None = None, **overrides: str) -> int:
    arguments = {
        "--scenario-type": "gnss-degradation",
        "--base-seed": str(BASE_SEED),
        "--runs": str(MIN_RUNS),
        "--data-dir": str(data_dir),
    }
    arguments.update(overrides)
    flat = [part for pair in arguments.items() for part in pair]
    return main(flat, env_file=env_file)


def test_a_manifest_without_a_corpus_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A manifest describes an extract that is gitignored and rebuilt, so the
    two go missing independently."""
    # spec: scn-003, adp-006
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"snapshot_hour": "2022-06-27T12:00:00Z"})
    )

    assert _invoke(tmp_path) == 2
    assert "opensky_extract.parquet" in capsys.readouterr().err


def test_a_manifest_with_no_snapshot_hour_exits_non_zero(
    tmp_path: Path, extract: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The span comes from the manifest rather than from the rows (`adp-001`),
    so a manifest that does not carry it cannot say where the corpus starts."""
    # spec: scn-003, adp-001
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    assert extract.parent == tmp_path  # the fixture writes it here
    (tmp_path / "manifest.json").write_text(json.dumps({"rows": 1}))

    assert _invoke(tmp_path) == 2


def test_a_missing_exclusion_list_exits_non_zero(
    tmp_path: Path, extract: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`adp-008`'s whole point, one level up. An empty list is the answer "no
    track carries a natural gap"; a missing file is "nobody looked", and a
    batch that treated the second as the first would stage coverage gaps on
    tracks that already have one -- making the false-positive rate for that
    type meaningless without anything appearing to go wrong."""
    # spec: scn-003, adp-008
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    assert extract.parent == tmp_path  # the fixture writes it here
    (tmp_path / "manifest.json").write_text(
        json.dumps({"snapshot_hour": "2022-06-27T12:00:00Z"})
    )

    assert _invoke(tmp_path) == 2


def test_the_seed_may_come_from_an_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both operator commands load `.env` rather than requiring an export, and
    this one follows `app/replay.py` rather than the server (`docs/qa.md` §37).
    Reaching the corpus check is the proof the seed was found."""
    # spec: scn-003, adp-007
    monkeypatch.delenv(SEED_ENV_VAR, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f"{SEED_ENV_VAR}=a-test-seed-not-the-real-one\n")

    assert _invoke(tmp_path, env_file=env_file) == 2
    assert SEED_ENV_VAR not in capsys.readouterr().err


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


@pytest.fixture()
def data_dir(tmp_path: Path, extract: Path) -> Path:
    """A data directory shaped like the real one: extract, manifest, exclusions."""
    directory = tmp_path / "opensky"
    directory.mkdir()
    shutil.copy(extract, directory / "opensky_extract.parquet")
    (directory / "manifest.json").write_text(
        json.dumps({"snapshot_hour": "2022-06-27T12:00:00Z"})
    )
    (directory / "natural_gaps.json").write_text(json.dumps({"gaps": []}))
    return directory


@pytest.mark.database
@requires_database
def test_the_command_runs_a_batch_end_to_end(
    data_dir: Path,
    migrated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole operator surface, against a real database.

    `adp-007` found two defects by running its command that no test could
    reach -- a path resolved against a directory that does not exist in the
    container, and an environment variable arriving as empty rather than
    absent. Both were in exactly this stretch of code.
    """
    # spec: scn-003, ops-003
    monkeypatch.setenv("DATABASE_URL", live_database_url())
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    buffer = io.StringIO()

    code = main(
        [
            "--scenario-type",
            "aircraft-coverage-gap",
            "--base-seed",
            str(BASE_SEED),
            "--runs",
            str(MIN_RUNS),
            "--duration-seconds",
            str(RUN_SECONDS),
            # The default incident starts 120 s into a run, which a sixty-second
            # run never reaches -- the batch refuses it, which is the guard two
            # tests below. A campaign turns these dials; so does this test.
            "--incident-offset-s",
            "10",
            "--incident-duration-s",
            "40",
            "--data-dir",
            str(data_dir),
        ],
        env_file=None,
        stdout=buffer,
    )

    assert code == 0
    assert _count(migrated_database, "scenario_runs") == MIN_RUNS
    assert _count(migrated_database, "scenario_runs", "completed_at IS NULL") == 0
    assert _count(migrated_database, "observations", "data_mode = 'synthetic'") > 0
    # The report names every run and the seed each one used, so a single run can
    # be reproduced without re-deriving the batch by hand.
    report = buffer.getvalue()
    assert str(BASE_SEED) in report
    assert report.count("ok") >= MIN_RUNS


@pytest.mark.database
@requires_database
def test_a_run_whose_row_cannot_be_opened_is_still_recorded(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """The other half of "recorded and skipped": a run can fail before it has
    an id, and a batch that let that propagate would abort on the first one."""
    # spec: scn-003

    summary = run_batch(
        layout,
        scenario_type=ScenarioType.NORMAL_BASELINE,
        base_seed=BASE_SEED,
        count=MIN_RUNS,
        corpus=CORPUS,
        duration_seconds=RUN_SECONDS,
        extract=extract,
        repository=PostgisObservationRepository(factory),
        pseudonymiser=PSEUDONYMISER,
        session_factory=_RefusesToOpenRuns(),  # type: ignore[arg-type]
    )

    assert summary.failed == MIN_RUNS
    assert all(run.run_id is None for run in summary.runs)
    assert all("no runs today" in (run.error or "") for run in summary.runs)
    assert _count(migrated_database, "scenario_runs") == 0


def test_a_batch_whose_incident_cannot_occur_is_refused(layout: RfLayout) -> None:
    """Found by running `make generate` for the first time, not by a test.

    Twenty runs of `aircraft-coverage-gap` reported ok with zero aircraft
    staged: a 120-second run with the default 120-second offset puts the whole
    incident after the run ends, so nothing is suppressed and no cell is raised.
    The readings were byte-identical to the quiet run's while the answer key
    claimed a scenario type -- twenty mislabelled controls, counted as evidence
    by anything that read the table. Refused up front rather than per run,
    because it is a property of the configuration and twenty identical failures
    are noise.
    """
    # spec: scn-003, scn-002, anom-008
    with pytest.raises(ValueError, match="stages nothing"):
        run_batch(
            layout,
            scenario_type=ScenarioType.AIRCRAFT_COVERAGE_GAP,
            base_seed=BASE_SEED,
            count=MIN_RUNS,
            corpus=CORPUS,
            duration_seconds=120,
            extract=Path("unused — the check happens first"),
            repository=FailingObservationRepository(),
            pseudonymiser=PSEUDONYMISER,
            session_factory=None,  # type: ignore[arg-type]
            incident=IncidentParameters(),
        )


def test_the_quiet_control_is_not_refused_for_an_incident_it_never_stages(
    layout: RfLayout,
) -> None:
    """The control carries incident parameters it does not use, so that a batch
    varying one says so on every row including the control. Refusing it for a
    staging that was never going to happen would make the control the one type
    that cannot be configured like the others."""
    # spec: scn-003, scn-002
    summary = run_batch(
        layout,
        scenario_type=ScenarioType.NORMAL_BASELINE,
        base_seed=BASE_SEED,
        count=MIN_RUNS,
        corpus=CORPUS,
        duration_seconds=120,
        extract=Path("/nonexistent"),
        repository=FailingObservationRepository(),
        pseudonymiser=PSEUDONYMISER,
        session_factory=_RefusesToOpenRuns(),  # type: ignore[arg-type]
        incident=IncidentParameters(),
    )

    # Every run fails on the refused session, which is this test's way of
    # reaching the loop at all -- what matters is that it reached the loop.
    assert len(summary.runs) == MIN_RUNS


@pytest.mark.database
@requires_database
def test_the_command_refuses_a_batch_that_would_stage_nothing(
    data_dir: Path,
    migrated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same refusal through the operator surface, which is where it would
    actually be met: `make generate` with a short duration and the default
    offset is exactly the invocation that produced twenty mislabelled runs."""
    # spec: scn-003
    monkeypatch.setenv("DATABASE_URL", live_database_url())
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")

    code = main(
        [
            "--scenario-type",
            "aircraft-coverage-gap",
            "--base-seed",
            str(BASE_SEED),
            "--runs",
            str(MIN_RUNS),
            "--duration-seconds",
            str(RUN_SECONDS),
            "--data-dir",
            str(data_dir),
        ],
        env_file=None,
    )

    assert code == 2
    assert "stages nothing" in capsys.readouterr().err
    assert _count(migrated_database, "scenario_runs") == 0


@pytest.mark.database
@requires_database
def test_a_run_is_not_marked_complete_when_only_its_first_half_landed(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """`db-007` again, at the seam this item creates. The radio grid commits in
    one act and the track window in its own, so a run can fail between them --
    and the completion stamp is the only thing that says so afterwards. A stamp
    written after the first half would mark that run finished while half its
    data was missing, which reads downstream as a receiver that went quiet."""
    # spec: scn-003, db-007

    class RefusesTheSecondWrite(PostgisObservationRepository):
        def __init__(self, session_factory: sessionmaker) -> None:
            super().__init__(session_factory)
            self.calls = 0

        def save_batch(self, observations: Any, quarantined: Any) -> None:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("the track half is not having it")
            super().save_batch(observations, quarantined)

    repository = RefusesTheSecondWrite(factory)
    outcome = _execute(layout, _spec(), extract, factory, repository=repository)

    assert repository.calls == 2
    assert not outcome.completed
    # The radio half it did write stays written -- nothing is deleted (db-007).
    assert _count(migrated_database, "observations", "observation_type = 'rf'") > 0
    (row,) = _run_rows(migrated_database)
    assert row.completed_at is None


class _FailsTheNthTransaction:
    """A session factory that refuses one transaction and passes the rest on.

    A run opens three: the row, the finished answer key, and the completion
    stamp. Refusing the *third* is what separates the two orders -- refusing the
    second does not, because whichever call happens to be second is the one that
    fails, and the run ends up looking the same either way. Found by mutation:
    the first version of this helper refused the second and left the swapped
    order green.
    """

    def __init__(self, inner: sessionmaker, nth: int) -> None:
        self._inner = inner
        self._nth = nth
        self.calls = 0

    def begin(self) -> Any:
        self.calls += 1
        if self.calls == self._nth:
            raise RuntimeError("the answer key is not having it")
        return self._inner.begin()


@pytest.mark.database
@requires_database
def test_the_completion_stamp_is_written_after_the_answer_key(
    layout: RfLayout, extract: Path, factory: sessionmaker, migrated_database: Engine
) -> None:
    """Written after a mutation showed the order was not asserted: swapping the
    answer key and the completion stamp left all twenty-six tests green.

    The order is load-bearing. The row is opened with what the run *intends* to
    stage; the finished key -- which names the aircraft actually touched -- is
    written at the end. A run stamped complete before that key lands is a run
    that claims to have finished while its answer key still says no aircraft
    were affected, and every one it really staged would be scored as a miss the
    detector was never shown.
    """
    # spec: scn-003, scn-002, db-007
    refusing = _FailsTheNthTransaction(factory, 3)

    outcome = execute_run(
        layout,
        _spec(),
        extract=extract,
        repository=PostgisObservationRepository(factory),
        pseudonymiser=PSEUDONYMISER,
        session_factory=refusing,  # type: ignore[arg-type]
    )

    assert not outcome.completed
    (row,) = _run_rows(migrated_database)
    # The stamp is the thing that must be missing. Under the swapped order it
    # would be present, because the stamp would have been written before the
    # call that failed.
    assert row.completed_at is None
    # And the finished key did land, naming what the run actually staged --
    # which is what makes this an assertion about order rather than about
    # failure.
    assert row.ground_truth["aircraft"]
