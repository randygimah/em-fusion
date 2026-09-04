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


def _settings(block: str) -> list[str]:
    """The lines of a block that are settings rather than commentary.

    Added during implementation, not before it: the first version of the two
    tests below searched every line mentioning the seed, and matched the
    explanatory comment written above the setting instead of the setting
    itself. That is the same defect as matching a docstring rather than an
    import (`docs/qa.md` section 38) -- a text search cannot tell a rule from a
    description of the rule. Recorded here because a test corrected after its
    implementation exists is a deviation from the workflow.
    """
    return [line for line in block.splitlines() if not line.strip().startswith("#")]


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


def test_the_seed_may_come_from_the_env_file(
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One of `adp-007`'s four fixed decisions: this CLI loads `.env`.

    It follows `app/corpus/build.py` rather than `app/main.py`, so the two
    operator commands behave alike and the server stays the single documented
    exception (`docs/qa.md` section 37). It matters more since the seed stopped
    being a required Compose variable: `backend/.env` is mounted into the
    container at `/app/.env`, so this is what makes `make replay` work without
    anyone exporting anything.

    Reaching the database means the seed was found, so an exit code of 1
    against the unreachable URL every test carries is the assertion. Added
    after the implementation, to close the one uncovered line in the module --
    a deviation from the workflow, recorded rather than quietly absorbed.
    """
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "placeholder-so-teardown-removes-it")
    monkeypatch.delenv(SEED_ENV_VAR)
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"{SEED_ENV_VAR}=a-test-seed-not-the-real-one\n", encoding="utf-8"
    )

    code = main(["--data-dir", str(data_dir)], env_file=env_file)

    assert code == 1
    assert SEED_ENV_VAR not in capsys.readouterr().err


def test_an_empty_seed_in_the_environment_does_not_shadow_the_env_file(
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Found by running `make replay`, not by this suite. Added 2026-09-04.

    Compose passes the seed through from the host, so an unset host variable
    arrives inside the container as `PSEUDONYM_SEED=""` -- present, and empty.
    `load_dotenv(override=False)` treats present-but-empty as present, so
    `/app/.env` was skipped and the replay failed with the seed sitting in a
    file two directories away. Every existing test either set the variable or
    deleted it; none set it to empty, which is the one state Compose actually
    produces.

    Recorded as a deviation: this test was written after the fix, because the
    fix was written after a real run. It is also the argument for `adp-007`
    existing at all -- the defect was unreachable from the test suite and
    obvious on first use.
    """
    # spec: adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "")
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"{SEED_ENV_VAR}=a-test-seed-not-the-real-one\n", encoding="utf-8"
    )

    code = main(["--data-dir", str(data_dir)], env_file=env_file)

    assert code == 1  # reached the unreachable database, so the seed was found
    assert SEED_ENV_VAR not in capsys.readouterr().err


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
        settings = _settings(_service_block(compose, service))
        assert any(SEED_ENV_VAR in line for line in settings)


def test_the_seed_is_passed_through_with_no_default_of_any_kind() -> None:
    """Substitution only: `${PSEUDONYM_SEED}`, never a value and never a default.

    `adp-007` originally specified Compose's required form, `${VAR:?}`, so that
    an unset seed failed on the host. **That was wrong and was corrected during
    implementation** (2026-09-04): Compose interpolates the entire file for
    every command regardless of profile, so a required variable here makes
    `up`, `migrate`, `test` and `demo` all demand a seed that only `replay`
    needs -- and `make demo` on a clean machine is `AC-12`. Verified: with the
    seed unset, `docker compose config` itself exits non-zero.

    The loud failure is not lost, it moved. `Pseudonymiser.from_environment`
    raises before anything is written, naming `backend/.env.example`, and
    `app/replay.py` loads `backend/.env`, so the ordinary path needs no export
    at all. `test_an_unset_seed_fails_before_the_database_is_touched` is the
    test that holds that guarantee.
    """
    # spec: adp-007
    compose = _read(COMPOSE_PATHS)

    for service in ("backend", "pipeline"):
        settings = _settings(_service_block(compose, service))
        line = next(entry for entry in settings if SEED_ENV_VAR in entry)
        assert line.split(":", 1)[1].strip() == f"${{{SEED_ENV_VAR}}}"


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
        for line in _settings(source):
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


# ------------------------------------------------- run completion, against the database


def _run_completed_at(engine: Engine) -> object:
    """The single run's `completed_at`, read on a connection of its own.

    Deliberately not the session the replay is writing through. Read inside
    that transaction it would show whatever the replay had done but not yet
    committed, and the property under test is what a *later* reader sees.
    """
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT completed_at FROM scenario_runs")
        ).scalar_one()


@pytest.mark.database
@requires_database
def test_a_finished_replay_marks_its_run_complete(
    data_dir: Path, replay_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: db-007, adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    monkeypatch.setenv(
        "DATABASE_URL", replay_database.url.render_as_string(hide_password=False)
    )

    code = main(["--data-dir", str(data_dir)], env_file=None)

    assert code == 0
    assert _run_completed_at(replay_database) is not None


@pytest.mark.database
@requires_database
def test_the_run_is_not_marked_complete_until_the_last_batch_commits(
    data_dir: Path, replay_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordering, observed from inside the writes rather than inferred.

    A flag written before the work records an intention, and an intention is
    indistinguishable from an outcome once the process is gone. The repository
    is replaced with one that reads the run's `completed_at` on each call, so a
    completion set up front shows up as a non-null observation partway through
    rather than as a passing test.
    """
    # spec: db-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    monkeypatch.setenv(
        "DATABASE_URL", replay_database.url.render_as_string(hide_password=False)
    )
    observed: list[object] = []

    class ObservesCompletion(PostgisObservationRepository):
        def save_batch(
            self,
            observations: Sequence[CanonicalObservation],
            quarantined: Sequence[QuarantineRecord],
        ) -> None:
            observed.append(_run_completed_at(replay_database))
            super().save_batch(observations, quarantined)

    monkeypatch.setattr("app.replay.PostgisObservationRepository", ObservesCompletion)

    code = main(["--data-dir", str(data_dir), "--window-seconds", "10"], env_file=None)

    assert code == 0
    assert len(observed) > 1
    assert observed == [None] * len(observed)
    assert _run_completed_at(replay_database) is not None


@pytest.mark.database
@requires_database
def test_an_interrupted_replay_leaves_its_run_incomplete(
    data_dir: Path, replay_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first named failure case, and the reason the column is nullable.

    `adp-007` made one window the unit of work, so a replay that dies part-way
    leaves its earlier batches committed. Those rows are kept -- they are
    evidence about what went wrong, and a cascading delete over the corpus is a
    surprising thing for a failure path to do -- so the run must instead be
    left unmarked, which is what makes the partial run findable afterwards.
    """
    # spec: db-007, adp-007
    monkeypatch.setenv(SEED_ENV_VAR, "a-test-seed-not-the-real-one")
    monkeypatch.setenv(
        "DATABASE_URL", replay_database.url.render_as_string(hide_password=False)
    )

    class FailsOnSecondBatch(PostgisObservationRepository):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.calls = 0

        def save_batch(
            self,
            observations: Sequence[CanonicalObservation],
            quarantined: Sequence[QuarantineRecord],
        ) -> None:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("the database is not having it")
            super().save_batch(observations, quarantined)

    monkeypatch.setattr("app.replay.PostgisObservationRepository", FailsOnSecondBatch)

    code = main(["--data-dir", str(data_dir), "--window-seconds", "10"], env_file=None)

    assert code == 1
    assert _count(replay_database, "scenario_runs") == 1
    assert _run_completed_at(replay_database) is None
    assert _count(replay_database, "observations") > 0


# Mutation result, 2026-09-04: moving `complete_scenario_run` in `main` to
# before the call to `replay` turned both the ordering test and the interrupted
# test red. That is the mutation worth guarding, because a flag set up front is
# not a visibly broken program -- every count still balances, the summary still
# prints, and the only thing that changes is that a run which died half-way
# through now claims to have finished.
