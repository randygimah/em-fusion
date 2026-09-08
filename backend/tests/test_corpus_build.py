"""Corpus build command-line entrypoint. Spec: adp-006.

The operator surface over adp-004 and adp-005. Fixtures are imported from
the adp-005 module rather than duplicated, because this command wraps that
function and the two must be exercised against the same shaped tarball.

The transport is injected and the module refuses sockets, for the reason
adp-005 gives: a suite that really downloads is slow, non-deterministic,
dependent on OpenSky's hosting, and turns CI into an unattended acceptor of
someone else's licence terms.
"""

import hashlib
import json
import socket
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.corpus.build import build_parser, main
from tests.test_corpus_fetch import (
    SNAPSHOT,
    _artefacts,
    _manifest_file,
    _opener_for,
    _refusing_opener,
    _row,
    _tar_bytes,
)

SEED = "a-test-seed-not-the-real-one"

BOX_IN_MANIFEST = {
    "lat_min": 47.0,
    "lat_max": 55.0,
    "lon_min": 3.0,
    "lon_max": 15.0,
}

TODAY = datetime.now(timezone.utc).date().isoformat()


@pytest.fixture(autouse=True)
def _no_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: adp-006 — inherited from adp-005's fourth failure case.
    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("no test in this module may open a socket")

    monkeypatch.setattr(socket, "socket", _refuse)


@pytest.fixture(autouse=True)
def _seed_in_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDONYM_SEED", SEED)


@pytest.fixture
def clone(tmp_path: Path) -> Iterator[tuple[Path, bytes]]:
    """A data directory holding only the committed manifest, as after a clone."""
    payload = _tar_bytes(
        [
            _row(time=1656331200),
            _row(time=1656331210),
            _row(time=1656331200, icao24="bbb222", lat="37.89"),
        ]
    )
    data_dir = tmp_path / "opensky"
    data_dir.mkdir()
    _manifest_file(
        data_dir,
        original_sha256=hashlib.sha256(payload).hexdigest(),
        content_sha256=None,
        bounding_box=BOX_IN_MANIFEST,
    )
    yield data_dir, payload


def _manifest(data_dir: Path) -> dict[str, Any]:
    return json.loads((data_dir / "manifest.json").read_text())


def _run(data_dir: Path, payload: bytes | None, *args: str, **kwargs: Any) -> int:
    opener = _opener_for(payload)[0] if payload is not None else _refusing_opener
    return main(
        ["--data-dir", str(data_dir), *args],
        opener=opener,
        **kwargs,
    )


def _place_raw(data_dir: Path, payload: bytes) -> Path:
    """Put the tarball where a previous run would have left it."""
    raw = data_dir / "raw" / f"{SNAPSHOT}.csv.tar"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(payload)
    return raw


# --- Licence acceptance -----------------------------------------------------


def test_the_notice_is_printed_and_nothing_is_written_without_acceptance(
    clone: tuple[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance offered without the terms is consent to nothing."""
    # spec: adp-006
    data_dir, payload = clone

    exit_code = _run(data_dir, payload)

    assert exit_code != 0
    assert "Data License Agreement" in capsys.readouterr().out
    assert _artefacts(data_dir) == {"manifest.json"}


def test_acceptance_cannot_be_given_by_an_environment_variable(
    clone: tuple[Path, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fifth failure case: acceptance is an act by the operator, so it
    cannot be pre-set in a shell profile or a CI configuration."""
    # spec: adp-006
    data_dir, payload = clone
    for name in ("ACCEPT_LICENCE", "ACCEPT_LICENSE", "OPENSKY_ACCEPT_LICENCE"):
        monkeypatch.setenv(name, "1")

    assert _run(data_dir, payload) != 0
    assert _artefacts(data_dir) == {"manifest.json"}


# --- The seed ---------------------------------------------------------------


def test_a_missing_seed_aborts_before_anything_is_written(
    clone: tuple[Path, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: adp-006
    data_dir, payload = clone
    monkeypatch.delenv("PSEUDONYM_SEED", raising=False)

    exit_code = _run(data_dir, payload, "--accept-licence", env_file=None)

    assert exit_code != 0
    assert _artefacts(data_dir) == {"manifest.json"}


def test_the_seed_is_not_a_command_line_flag() -> None:
    """The sixth failure case. A flag is recorded in shell history and is
    visible in a process listing, so the key would leak from either."""
    # spec: adp-006
    rendered = build_parser().format_help()

    # Assert the parser is populated first: an empty one trivially contains
    # no --seed, and the test would pass against a stub.
    for expected in ("--data-dir", "--accept-licence", "--box", "--replace-corpus"):
        assert expected in rendered, expected

    assert "--seed" not in rendered
    assert "--pseudonym-seed" not in rendered


def test_the_summary_prints_the_fingerprint_and_never_the_seed(
    clone: tuple[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    # spec: adp-006
    data_dir, payload = clone

    assert _run(data_dir, payload, "--accept-licence") == 0

    out = capsys.readouterr().out
    assert SEED not in out
    assert hashlib.sha256(SEED.encode()).hexdigest() in out


def test_the_seed_is_read_from_the_env_file_when_absent_from_the_environment(
    clone: tuple[Path, bytes], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seed lives in backend/.env, so the command should not need it
    exported by hand."""
    # spec: adp-006
    data_dir, payload = clone
    monkeypatch.delenv("PSEUDONYM_SEED", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f"PSEUDONYM_SEED={SEED}\n")

    exit_code = _run(data_dir, payload, "--accept-licence", env_file=env_file)

    assert exit_code == 0
    assert _manifest(data_dir)["pseudonym_seed_sha256"] == (
        hashlib.sha256(SEED.encode()).hexdigest()
    )


# --- The derived download date ----------------------------------------------


def test_a_skipped_download_carries_the_recorded_date_forward(
    clone: tuple[Path, bytes],
) -> None:
    """The first failure case, and the trap the manual invocation carried:
    re-filtering a file downloaded weeks ago must not claim it arrived today."""
    # spec: adp-006
    data_dir, payload = clone
    _place_raw(data_dir, payload)
    recorded = _manifest(data_dir)["download_date"]

    # The refusing opener proves the transport was never reached.
    assert _run(data_dir, None, "--accept-licence") == 0

    assert _manifest(data_dir)["download_date"] == recorded
    assert recorded != TODAY


def test_an_actual_download_records_today(clone: tuple[Path, bytes]) -> None:
    # spec: adp-006
    data_dir, payload = clone

    assert _run(data_dir, payload, "--accept-licence") == 0

    assert _manifest(data_dir)["download_date"] == TODAY


# --- The bounding box -------------------------------------------------------


def test_the_box_defaults_to_the_one_recorded_in_the_manifest(
    clone: tuple[Path, bytes],
) -> None:
    """The manifest is the authority on what the corpus covers, so a
    re-filter cannot silently apply a different box from the one that built
    the extract it is replacing."""
    # spec: adp-006
    data_dir, payload = clone

    assert _run(data_dir, payload, "--accept-licence") == 0

    assert _manifest(data_dir)["bounding_box"] == BOX_IN_MANIFEST


def test_an_explicit_box_overrides_the_manifest(clone: tuple[Path, bytes]) -> None:
    # spec: adp-006
    data_dir, payload = clone

    exit_code = _run(
        data_dir, payload, "--accept-licence", "--box", "49", "54", "3", "11"
    )

    assert exit_code == 0
    assert _manifest(data_dir)["bounding_box"] == {
        "lat_min": 49.0,
        "lat_max": 54.0,
        "lon_min": 3.0,
        "lon_max": 11.0,
    }


# --- The content-checksum guard ---------------------------------------------


def test_a_changed_content_checksum_aborts_and_writes_nothing(
    clone: tuple[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    """The second failure case: silently replacing the corpus that every
    reported measurement was taken against."""
    # spec: adp-006
    data_dir, payload = clone
    _manifest_file(
        data_dir,
        original_sha256=hashlib.sha256(payload).hexdigest(),
        content_sha256="9" * 64,
        bounding_box=BOX_IN_MANIFEST,
    )
    before = (data_dir / "manifest.json").read_text()

    exit_code = _run(data_dir, payload, "--accept-licence")

    assert exit_code != 0
    assert (data_dir / "manifest.json").read_text() == before
    assert not (data_dir / "opensky_extract.parquet").exists()
    assert not (data_dir / "coverage.json").exists()


def test_the_abort_reports_both_checksums(
    clone: tuple[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    """An abort that does not say what changed cannot be acted on."""
    # spec: adp-006
    data_dir, payload = clone
    _manifest_file(
        data_dir,
        original_sha256=hashlib.sha256(payload).hexdigest(),
        content_sha256="9" * 64,
        bounding_box=BOX_IN_MANIFEST,
    )

    _run(data_dir, payload, "--accept-licence")

    rendered = capsys.readouterr()
    assert "9" * 64 in rendered.out + rendered.err


def test_replace_corpus_lets_a_deliberate_change_through(
    clone: tuple[Path, bytes],
) -> None:
    """Replacing the corpus is permitted, but only as an explicit act."""
    # spec: adp-006
    data_dir, payload = clone
    _manifest_file(
        data_dir,
        original_sha256=hashlib.sha256(payload).hexdigest(),
        content_sha256="9" * 64,
        bounding_box=BOX_IN_MANIFEST,
    )

    exit_code = _run(data_dir, payload, "--accept-licence", "--replace-corpus")

    assert exit_code == 0
    assert _manifest(data_dir)["content_sha256"] != "9" * 64


# --- Ordinary success and failure -------------------------------------------


def test_a_successful_run_exits_zero_and_writes_the_three_artefacts(
    clone: tuple[Path, bytes],
) -> None:
    # spec: adp-006
    data_dir, payload = clone

    assert _run(data_dir, payload, "--accept-licence") == 0

    assert _artefacts(data_dir) == {
        f"raw/{SNAPSHOT}.csv.tar",
        "opensky_extract.parquet",
        "manifest.json",
        "coverage.json",
        "natural_gaps.json",
    }


def test_the_run_writes_the_injection_exclusion_list(
    clone: tuple[Path, bytes],
) -> None:
    """The list scenario type 4 refuses injection sites from. Spec: adp-008.

    Written on every build, including when nothing qualifies: an empty list is
    the answer "no track carries a natural gap", and an absent file is the
    answer "nobody looked", which the generator cannot tell apart.
    """
    # spec: adp-008, adp-006
    data_dir, payload = clone

    assert _run(data_dir, payload, "--accept-licence") == 0

    report = json.loads((data_dir / "natural_gaps.json").read_text())
    assert isinstance(report["gaps"], list)
    assert report["bounding_box"] == BOX_IN_MANIFEST
    # Regenerated against the same seed as the extract it describes, so a seed
    # change is visible here as well as in the manifest.
    assert (
        report["pseudonym_seed_sha256"] == _manifest(data_dir)["pseudonym_seed_sha256"]
    )


def test_the_summary_names_what_was_written(
    clone: tuple[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    # spec: adp-006
    data_dir, payload = clone

    _run(data_dir, payload, "--accept-licence")

    out = capsys.readouterr().out
    assert "opensky_extract.parquet" in out
    assert "manifest.json" in out
    assert "coverage.json" in out
    assert "natural_gaps.json" in out
    assert _manifest(data_dir)["content_sha256"] in out


def test_a_download_checksum_mismatch_exits_non_zero(clone: tuple[Path, bytes]) -> None:
    """The command must not report success when adp-005 refused the bytes."""
    # spec: adp-006
    data_dir, _ = clone

    exit_code = _run(
        data_dir, b"not the tarball the manifest cites", "--accept-licence"
    )

    assert exit_code != 0
    assert _artefacts(data_dir) == {"manifest.json"}


def test_a_missing_manifest_exits_non_zero_rather_than_raising(tmp_path: Path) -> None:
    """The fourth failure case is about exit codes: a command usable in a
    script reports failure rather than a traceback."""
    # spec: adp-006
    empty = tmp_path / "opensky"
    empty.mkdir()

    assert _run(empty, None, "--accept-licence") != 0


def test_a_manifest_without_a_usable_box_asks_for_one_rather_than_guessing(
    clone: tuple[Path, bytes], capsys: pytest.CaptureFixture[str]
) -> None:
    """Falling back to a hard-coded box would silently filter to a region
    other than the one the manifest describes."""
    # spec: adp-006
    data_dir, payload = clone
    _manifest_file(
        data_dir,
        original_sha256=hashlib.sha256(payload).hexdigest(),
        content_sha256=None,
        bounding_box={},
    )

    exit_code = _run(data_dir, payload, "--accept-licence")

    assert exit_code != 0
    assert "--box" in capsys.readouterr().err
    assert not (data_dir / "opensky_extract.parquet").exists()
