"""Replay entrypoint, the operator surface over the adapter and the DAL. Spec: adp-007.

Four kinds of test, and the split is the same one `db-003` uses.

**Pure**, over window tiling and the summary. Tiling is where an off-by-one
turns into a duplicated or a missing frame, and both read downstream as
detection signal rather than as a bug -- a duplicate is a zero-second gap, a
hole is a dropout indistinguishable from the one scenario type 4 injects.

**Failure paths through `main`**, which need no database because they must all
fail before reaching one. The unreachable `DATABASE_URL` every test already
carries (`conftest`) is what makes the connection-failure case a unit test.

**Behaviour against a live database**, marked and skipped without one.

**Structural**, over `compose.yaml` and the root `Makefile`. Same weaker class
of evidence as `ops-003`'s tests and the same justification: they cannot prove
a command works against a daemon, but they can prove the seed is not committed
and that a target is not silently doing nothing.

`compose.yaml` is not mounted into the backend container -- Compose mounts
`./backend:/app` -- so `test-backend` grows a read-only mount for it, exactly
as `ops-003` did for the Makefile. Skipping here would be the failure these
tests exist to catch, one level up.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.adapters.opensky import Window
from app.corpus.extract import write_parquet
from app.dal.models import CanonicalObservation
from app.dal.pseudonymise import SEED_ENV_VAR, Pseudonymiser
from app.dal.repository import QuarantineRecord
from app.db.migrations import alembic_config
from app.db.repository import PostgisObservationRepository
from app.replay import (
    REPLAY_SCENARIO_TYPE,
    ReplaySummary,
    build_parser,
    main,
    replay,
    windows,
)
from tests.conftest import live_database_url, requires_database

HOUR_START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
EPOCH_START = int(HOUR_START.timestamp())

#: Never the corpus seed: `dal-004` forbids committing that value.
PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")

#: The identifiers the fixture rows carry. They are real-shaped on purpose --
#: the adapter emits them unchanged, and the substitution can only be proven
#: against a value that actually reached the DAL.
SOURCE_ICAO24 = "3c6444"
SOURCE_CALLSIGN = "DLH8AT"

#: Native checkout, then the read-only mounts used inside the container.
COMPOSE_PATHS = (
    Path(__file__).resolve().parents[2] / "compose.yaml",
    Path("/repo/compose.yaml"),
)
MAKEFILE_PATHS = (
    Path(__file__).resolve().parents[2] / "Makefile",
    Path("/repo/Makefile"),
)


# ------------------------------------------------------------------- helpers


def _read(candidates: Sequence[Path]) -> str:
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise AssertionError(  # pragma: no cover -- a broken checkout or mount
        f"not found at any of {[str(p) for p in candidates]}. Skipping is "
        "deliberately not an option here: see the module docstring."
    )


def _service_block(compose: str, service: str) -> str:
    """The lines belonging to one service, by indentation.

    PyYAML is not a dependency and is not being added for a test, so the file
    is read structurally rather than parsed. The limit that leaves is real and
    is stated in the module docstring.
    """
    lines = compose.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.strip() == f"{service}:"
    )
    indent = len(lines[start]) - len(lines[start].lstrip())
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        block.append(line)
    return "\n".join(block)


def _row(offset_s: int, **overrides: Any) -> dict[str, str]:
    """One extract row as CSV cells, the shape `write_parquet` coerces."""
    row = {
        "time": str(EPOCH_START + offset_s),
        "icao24": SOURCE_ICAO24,
        "lat": "51.09",
        "lon": "7.54",
        "velocity": "194.26",
        "heading": "135.64",
        "vertrate": "13.32",
        "callsign": f"{SOURCE_CALLSIGN}  ",
        "onground": "false",
        "alert": "false",
        "spi": "false",
        "squawk": "1000",
        "baroaltitude": "5753.1",
        "geoaltitude": "5951.22",
        "lastposupdate": str(EPOCH_START + offset_s - 2),
        "lastcontact": str(EPOCH_START + offset_s - 1),
    }
    row.update(overrides)
    return row


def _span(from_s: int, to_s: int) -> Window:
    return Window(
        start=HOUR_START + timedelta(seconds=from_s),
        end=HOUR_START + timedelta(seconds=to_s),
    )


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A manifest and a four-frame extract, the shape `main` expects on disk.

    One row has no position, so every run through this fixture exercises the
    quarantine path as well as the accept path -- the real corpus carries 500
    such rows for the same reason.
    """
    directory = tmp_path / "opensky"
    directory.mkdir()
    (directory / "manifest.json").write_text(
        json.dumps({"snapshot_hour": "2022-06-27T12:00:00Z"}), encoding="utf-8"
    )
    write_parquet(
        [_row(0), _row(10), _row(20), _row(30, lat="", lon="")],
        directory / "opensky_extract.parquet",
    )
    return directory


@pytest.fixture
def replay_database() -> Engine:
    """An empty schema brought to head. No scenario run: replay makes its own."""
    engine = create_engine(live_database_url(), poolclass=NullPool)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.commit()
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        engine.dispose()


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        )


# --------------------------------------------------------------- window tiling


def test_windows_tile_the_span_exactly_once() -> None:
    """Adjacent windows meet, and never overlap.

    `Window` is half-open by construction for this reason, but the tiling is
    what decides whether that property is used correctly. An overlap duplicates
    a frame, which reads downstream as a zero-second inter-sample gap; a hole
    manufactures a dropout indistinguishable from the injected one.
    """
    # spec: adp-007
    tiles = windows(_span(0, 300), seconds=100)

    assert [(w.start, w.end) for w in tiles] == [
        (HOUR_START, HOUR_START + timedelta(seconds=100)),
        (HOUR_START + timedelta(seconds=100), HOUR_START + timedelta(seconds=200)),
        (HOUR_START + timedelta(seconds=200), HOUR_START + timedelta(seconds=300)),
    ]


def test_the_final_window_is_truncated_to_the_span_end() -> None:
    """A span that does not divide evenly must not replay past its own end.

    Rounding the last window up would ask the reader for frames the corpus
    does not contain -- harmless here, and not harmless once a scenario run
    is bounded by simulated time.
    """
    # spec: adp-007
    tiles = windows(_span(0, 250), seconds=100)

    assert len(tiles) == 3
    assert tiles[-1].start == HOUR_START + timedelta(seconds=200)
    assert tiles[-1].end == HOUR_START + timedelta(seconds=250)


def test_a_window_longer_than_the_span_yields_one_window() -> None:
    # spec: adp-007
    tiles = windows(_span(0, 60), seconds=3600)

    assert len(tiles) == 1
    assert tiles[0] == _span(0, 60)


def test_a_zero_or_negative_window_is_refused() -> None:
    """Zero would tile forever; negative would tile backwards."""
    # spec: adp-007
    with pytest.raises(ValueError):
        windows(_span(0, 60), seconds=0)


# ------------------------------------------------------------------- summary


def test_a_summary_that_does_not_balance_cannot_be_constructed() -> None:
    """`dal-002`'s guarantee, reduced to arithmetic at run scale.

    Nothing is silently dropped means every row read left as either an
    observation or a quarantine record. Enforced on the model rather than
    checked at the call site, so a summary that fails it cannot be printed,
    returned, or written to a thesis table.
    """
    # spec: adp-007
    with pytest.raises(ValidationError):
        ReplaySummary(rows_read=10, accepted=7, quarantined=2, batches=1, seconds=0.1)


def test_a_balanced_summary_is_accepted() -> None:
    # spec: adp-007
    summary = ReplaySummary(
        rows_read=10, accepted=7, quarantined=3, batches=1, seconds=0.1
    )

    assert summary.rows_read == summary.accepted + summary.quarantined


def test_the_parser_carries_the_documented_defaults() -> None:
    # spec: adp-007
    args = build_parser().parse_args([])

    assert args.window_seconds > 0
    assert args.start is None
    assert args.end is None


# ------------------------------------------------- failure paths through main


def test_an_unset_seed_fails_before_the_database_is_touched(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dal-004`: no default, no empty fallback, and nothing written first.

    Ordering is the assertion. A replay that connected, created its run row and
    then failed on the seed would leave an orphan run behind, and a replay that
    fell back to an empty seed would produce a corpus whose pseudonyms cannot
    be reconciled with any other run.
    """
    # spec: adp-007
    monkeypatch.delenv(SEED_ENV_VAR, raising=False)
    built: list[str] = []
    monkeypatch.setattr(
        "app.replay.init_engine", lambda: built.append("engine")  # type: ignore[arg-type]
    )

    code = main(["--data-dir", str(data_dir)], env_file=None)

    assert code != 0
    assert built == []
    assert SEED_ENV_VAR in capsys.readouterr().err


def test_a_missing_manifest_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")

    code = main(["--data-dir", str(tmp_path)], env_file=None)

    assert code != 0
    assert "manifest.json" in capsys.readouterr().err


def test_a_missing_extract_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The manifest is present and the artefact it describes is not.

    A distinct case from the one above, because the corpus is gitignored: this
    is what a fresh clone looks like before `python -m app.corpus.build` runs,
    and the message has to say so rather than report a parquet error.
    """
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"snapshot_hour": "2022-06-27T12:00:00Z"}), encoding="utf-8"
    )

    code = main(["--data-dir", str(tmp_path)], env_file=None)

    assert code != 0
    assert "opensky_extract.parquet" in capsys.readouterr().err


def test_a_window_outside_the_corpus_span_exits_non_zero(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Replaying a span the corpus does not cover writes nothing.

    Exiting zero over it would report a successful run that produced no
    observations, which is the shape of a silent failure rather than a loud
    one.
    """
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")

    code = main(
        [
            "--data-dir",
            str(data_dir),
            "--start",
            "2030-01-01T00:00:00+00:00",
            "--end",
            "2030-01-01T01:00:00+00:00",
        ],
        env_file=None,
    )

    assert code != 0
    assert "span" in capsys.readouterr().err.lower()


def test_an_unreachable_database_exits_non_zero(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A unit test only because `conftest` already points every test at a
    port where nothing listens."""
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")

    code = main(["--data-dir", str(data_dir)], env_file=None)

    assert code != 0
    assert capsys.readouterr().err.strip()


# ------------------------------------------------------- against the database


@pytest.mark.database
@requires_database
def test_replay_persists_the_corpus_and_creates_its_own_run(
    data_dir: Path, replay_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    monkeypatch.setenv(
        "DATABASE_URL", replay_database.url.render_as_string(hide_password=False)
    )

    code = main(["--data-dir", str(data_dir)], env_file=None)

    assert code == 0
    assert _count(replay_database, "scenario_runs") == 1
    assert _count(replay_database, "observations") == 3
    assert _count(replay_database, "quarantined_records") == 1


@pytest.mark.database
@requires_database
def test_the_run_row_is_identifiable_as_a_replay(
    data_dir: Path, replay_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`scn-001` supersedes this row, and has to be able to find it.

    A replay-created run is a placeholder standing in for a scenario the
    generator does not exist to produce yet. Written with a scenario type
    nothing else uses, so those rows are a query rather than an archaeology
    exercise once the generator lands. Ground truth is null because a replay
    injects nothing, and `api-009` requires it never leave the run record
    regardless.
    """
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    monkeypatch.setenv(
        "DATABASE_URL", replay_database.url.render_as_string(hide_password=False)
    )

    main(["--data-dir", str(data_dir)], env_file=None)

    with replay_database.connect() as connection:
        row = connection.execute(
            text("SELECT scenario_type, seed, ground_truth FROM scenario_runs")
        ).one()

    assert row.scenario_type == REPLAY_SCENARIO_TYPE
    assert row.seed == 0
    assert row.ground_truth is None


@pytest.mark.database
@requires_database
def test_the_reported_counts_sum_to_the_rows_read(
    data_dir: Path,
    replay_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The summary is a measurement that reaches the write-up, so it is
    asserted against the rows in the database rather than against itself."""
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    monkeypatch.setenv(
        "DATABASE_URL", replay_database.url.render_as_string(hide_password=False)
    )

    main(["--data-dir", str(data_dir)], env_file=None)
    printed = capsys.readouterr().out

    stored = _count(replay_database, "observations") + _count(
        replay_database, "quarantined_records"
    )
    assert "4" in printed
    assert stored == 4


@pytest.mark.database
@requires_database
def test_no_real_identifier_survives_the_replay(
    data_dir: Path, replay_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dal-004` over the whole path, not over one call.

    The fixture rows carry a real-shaped `icao24` and callsign because the
    adapter emits them unchanged -- the DAL can only substitute an identifier
    that reaches it. This is the only test in the repository that proves the
    substitution holds for a record that entered as a file on disk.
    """
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    monkeypatch.setenv(
        "DATABASE_URL", replay_database.url.render_as_string(hide_password=False)
    )

    main(["--data-dir", str(data_dir)], env_file=None)

    with replay_database.connect() as connection:
        payloads = connection.execute(
            text("SELECT payload::text FROM observations")
        ).scalars()
        blob = " ".join(payloads)

    assert SOURCE_ICAO24 not in blob
    assert SOURCE_CALLSIGN not in blob
    assert "icao24" not in blob
    assert "callsign" not in blob


@pytest.mark.database
@requires_database
def test_a_short_window_writes_more_than_one_batch(
    data_dir: Path,
    replay_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The window length is what decides the unit of work, so it has to be a
    parameter with a visible effect rather than a constant."""
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    monkeypatch.setenv(
        "DATABASE_URL", replay_database.url.render_as_string(hide_password=False)
    )

    main(["--data-dir", str(data_dir), "--window-seconds", "10"], env_file=None)

    assert _count(replay_database, "observations") == 3
    assert re.search(r"batches\D+([2-9]|\d\d)", capsys.readouterr().out)


@pytest.mark.database
@requires_database
def test_an_interrupted_replay_leaves_earlier_windows_written(
    data_dir: Path, replay_database: Engine
) -> None:
    """The documented weakening of `dal-002`, asserted rather than assumed.

    The all-or-nothing guarantee is per batch, not per run: `adp-007` chose one
    window as the unit of work over a single transaction spanning the whole
    hour. The consequence is that an interrupted run leaves the windows already
    written in place, and a caller must not read a failed replay as having
    written nothing. Stated in the spec, so it is tested here rather than
    discovered by someone re-running a replay and finding duplicates.
    """
    # spec: adp-007

    class FailsOnThirdBatch(PostgisObservationRepository):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.calls = 0

        def save_batch(
            self,
            observations: Sequence[CanonicalObservation],
            quarantined: Sequence[QuarantineRecord],
        ) -> None:
            self.calls += 1
            if self.calls == 3:
                raise RuntimeError("the database is not having it")
            super().save_batch(observations, quarantined)

    factory = sessionmaker(bind=replay_database, autoflush=False)
    with replay_database.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at) "
                "VALUES (1, :kind, '{}'::jsonb, 0, now())"
            ),
            {"kind": REPLAY_SCENARIO_TYPE},
        )
        connection.commit()

    with pytest.raises(RuntimeError):
        replay(
            path=data_dir / "opensky_extract.parquet",
            spans=windows(_span(0, 40), seconds=10),
            scenario_run_id=1,
            repository=FailsOnThirdBatch(factory),
            pseudonymiser=PSEUDONYMISER,
        )

    assert _count(replay_database, "observations") == 2


# ------------------------------------------------------------- compose and make


def test_the_seed_reaches_the_services_that_ingest() -> None:
    """Replay pseudonymises at ingest, so the container needs the seed.

    Before this item nothing running inside a container called the
    pseudonymiser -- the corpus is built natively -- so `compose.yaml` passed
    `DATABASE_URL` and nothing else. The trap was recorded in `docs/qa.md`
    section 37 a week before it could bite.
    """
    # spec: adp-007
    compose = _read(COMPOSE_PATHS)

    for service in ("backend", "pipeline"):
        assert SEED_ENV_VAR in _service_block(compose, service)


def test_an_unset_seed_fails_on_the_host_rather_than_in_the_container() -> None:
    """The `${VAR:?}` form, so Compose refuses before the container starts.

    Plain `${VAR}` substitutes empty, the container starts, and the failure
    surfaces from inside it with a message about configuration held outside the
    repository -- which locates the problem one machine away from the person
    who can fix it.
    """
    # spec: adp-007
    compose = _read(COMPOSE_PATHS)

    for service in ("backend", "pipeline"):
        block = _service_block(compose, service)
        line = next(entry for entry in block.splitlines() if SEED_ENV_VAR in entry)
        assert f"${{{SEED_ENV_VAR}:?" in line


def test_no_seed_value_is_committed_anywhere_in_the_command_surface() -> None:
    """`dal-004`: the seed is a key, and a committed key is a reverse mapping.

    An `icao24` is a 24-bit space of about 16.7 million values, so anyone
    holding the seed reconstructs the whole mapping by exhaustive search in
    seconds. A default in a compose file is a committed seed however it is
    spelled.

    Asserts an absence, so it passes on the day it is written. Mutation-tested
    2026-09-04, both spellings: a literal `PSEUDONYM_SEED: <value>` and a
    `${PSEUDONYM_SEED:-fallback}` default each turn it red. The second is the
    one worth running -- Compose's `:-` form reads as a safe default and is
    exactly how a committed seed would arrive by accident.
    """
    # spec: adp-007
    for source in (_read(COMPOSE_PATHS), _read(MAKEFILE_PATHS)):
        for line in source.splitlines():
            if SEED_ENV_VAR not in line:
                continue
            assert not re.search(rf"{SEED_ENV_VAR}\s*[:=]\s*\S", line) or "${" in line
            assert ":-" not in line


def test_replay_does_not_borrow_the_pipeline_service() -> None:
    """`make generate` runs the `pipeline` service, whose command names
    `app.pipeline` -- a module that does not exist until `scn-003`.

    Pointing `replay` at that service would make the target work by changing
    what the service means, and would leave `generate` broken behind a name
    that now appears to be used. `replay` runs the backend service instead,
    mirroring `migrate`.
    """
    # spec: adp-007
    makefile = _read(MAKEFILE_PATHS)
    recipe = re.search(r"^replay:.*?(?=^\S|\Z)", makefile, re.M | re.S)

    assert recipe is not None
    assert "app.replay" in recipe.group(0)
    assert "--profile pipeline" not in recipe.group(0)
