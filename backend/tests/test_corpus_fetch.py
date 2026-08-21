"""OpenSky corpus fetch tests.

Every test here proves part of adp-005. The transport is injected, never real:
a module-wide fixture below arms `socket.socket` to raise, so a test that
reached the network would fail rather than quietly succeed slowly. That is the
spec's fourth failure case, and it is enforced for the whole module rather than
asserted once.
"""

import gzip
import hashlib
import io
import json
import socket
import tarfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from app.corpus.extract import BoundingBox
from app.corpus.fetch import (
    ChecksumMismatchError,
    LicenceNotAcceptedError,
    build_corpus,
    download,
    file_sha256,
    licence_notice,
    read_source_ref,
)
from app.dal.pseudonymise import Pseudonymiser

COLUMNS = (
    "time,icao24,lat,lon,velocity,heading,vertrate,callsign,onground,alert,"
    "spi,squawk,baroaltitude,geoaltitude,lastposupdate,lastcontact"
)

# The manifest records this object's fingerprint, never its seed (dal-004).
PSEUDONYMISER = Pseudonymiser(seed="a-test-seed")

BOX = BoundingBox(lat_min=47.0, lat_max=55.0, lon_min=3.0, lon_max=15.0)

SNAPSHOT = "states_2022-06-27-12"
SOURCE_URL = f"https://s3.opensky-network.org/data-samples/{SNAPSHOT}.csv.tar"


# --------------------------------------------------------------------------
# The offline guarantee, armed for every test in the module
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec: adp-005 — the fourth failure case. A suite that really downloads is
    # slow, non-deterministic, dependent on OpenSky's hosting, and turns CI into
    # an unattended acceptor of someone else's licence terms.
    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("no test in this module may open a socket")

    monkeypatch.setattr(socket, "socket", _refuse)


def test_the_socket_ban_is_actually_armed() -> None:
    # spec: adp-005 — without this, every other test in the module passes
    # whether the fixture works or not, and the offline guarantee is decoration.
    with pytest.raises(AssertionError, match="socket"):
        socket.socket()


# --------------------------------------------------------------------------
# Fixtures: a corpus small enough to hash in a millisecond
# --------------------------------------------------------------------------


def _row(time: int = 1656331200, icao24: str = "4d22ec", lat: str = "51.09") -> str:
    """One CSV line in the published column order."""
    return (
        f"{time},{icao24},{lat},7.54,194.26,135.64,13.32,CXI27NM ,"
        f"False,False,False,2556,5753.1,5951.22,{time - 1}.94,{time}.0"
    )


def _tar_bytes(rows: list[str]) -> bytes:
    """A tarball shaped like the published one, in memory rather than on disk."""
    body = "\n".join([COLUMNS, *rows]) + "\n"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for member_name, payload in (
            (f"{SNAPSHOT}.csv.gz", gzip.compress(body.encode())),
            ("LICENSE.txt", b"General Terms of Use & Data License Agreement\n"),
            ("README.txt", b"OpenSky Data Sample\n"),
        ):
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _opener_for(payload: bytes) -> tuple[Callable[[str], BinaryIO], list[str]]:
    """A stand-in transport, plus the list of URLs it was asked for."""
    calls: list[str] = []

    def _open(url: str) -> BinaryIO:
        calls.append(url)
        return io.BytesIO(payload)

    return _open, calls


def _refusing_opener(*args: object, **kwargs: object) -> BinaryIO:
    """A transport that fails the test if anything reaches it."""
    raise AssertionError("the transport must not be used on this path")


def _manifest_file(directory: Path, **overrides: Any) -> Path:
    """The committed manifest, holding the pointer to the source."""
    manifest = {
        "source_url": SOURCE_URL,
        "snapshot_hour": "2022-06-27T12:00:00Z",
        "download_date": "2026-08-13",
        "original_sha256": "0" * 64,
        "content_sha256": "1" * 64,
        "licence": {"name": "OpenSky"},
        "attribution": "The OpenSky Network",
        "bounding_box": {},
        "null_sample": 0,
        "null_retained": 0,
    }
    manifest.update(overrides)
    for key, value in list(overrides.items()):
        if value is None:
            del manifest[key]

    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def _artefacts(directory: Path) -> set[str]:
    """Every file under a directory, relative and sorted for readable diffs."""
    return {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}


# --------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------


def test_file_sha256_matches_hashlib_across_chunk_boundaries(tmp_path: Path) -> None:
    # spec: adp-005 — the real file is ~180 MB, so it is hashed in chunks rather
    # than read into memory. A chunked hash that drops or repeats a boundary
    # still returns a plausible-looking digest, and would reject every good
    # download.
    payload = bytes(range(256)) * 40
    path = tmp_path / "blob.bin"
    path.write_bytes(payload)

    assert file_sha256(path, chunk_bytes=7) == hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------
# Licence acceptance: a gate on the operator, not a check on the data
# --------------------------------------------------------------------------


def test_downloading_without_licence_acceptance_is_refused(tmp_path: Path) -> None:
    # spec: adp-005 — the third failure case. Fetching on an unspoken assumption
    # of consent takes a licence action on the operator's behalf, which is the
    # thing not committing the extract exists to avoid.
    destination = tmp_path / "raw" / f"{SNAPSHOT}.csv.tar"

    with pytest.raises(LicenceNotAcceptedError):
        download(
            SOURCE_URL,
            destination,
            expected_sha256="0" * 64,
            accept_licence=False,
            opener=_refusing_opener,
        )

    assert not destination.exists()


def test_licence_acceptance_is_refused_by_default(tmp_path: Path) -> None:
    # spec: adp-005 — acceptance is an explicit act. A default that permits the
    # download is the same bypass with an extra argument in front of it.
    with pytest.raises(LicenceNotAcceptedError):
        download(
            SOURCE_URL,
            tmp_path / f"{SNAPSHOT}.csv.tar",
            expected_sha256="0" * 64,
            opener=_refusing_opener,
        )


def test_the_licence_notice_carries_the_governing_terms_and_attribution() -> None:
    # spec: adp-005 — acceptance shown without the terms is a consent dialogue
    # with nothing to consent to. §4(i) attribution is displayed at the same
    # point, because the obligation begins with the download, not with the
    # write-up.
    notice = licence_notice()

    assert "https://opensky-network.org/about/terms-of-use" in notice
    assert "OpenSky Network" in notice
    assert "Schäfer" in notice


# --------------------------------------------------------------------------
# Download: verify before the file is anywhere a later run would trust it
# --------------------------------------------------------------------------


def test_a_verified_download_lands_at_the_destination(tmp_path: Path) -> None:
    # spec: adp-005
    payload = _tar_bytes([_row()])
    opener, calls = _opener_for(payload)
    destination = tmp_path / "raw" / f"{SNAPSHOT}.csv.tar"

    result = download(
        SOURCE_URL,
        destination,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        accept_licence=True,
        opener=opener,
    )

    assert result == destination
    assert destination.read_bytes() == payload
    assert calls == [SOURCE_URL]


def test_a_checksum_mismatch_aborts_and_writes_nothing(tmp_path: Path) -> None:
    # spec: adp-005 — the first failure case. A file that does not match the
    # recorded checksum is not the source the manifest cites, and anything built
    # from it asserts a provenance that does not hold.
    opener, _ = _opener_for(b"not the published tarball")
    destination = tmp_path / "raw" / f"{SNAPSHOT}.csv.tar"

    with pytest.raises(ChecksumMismatchError):
        download(
            SOURCE_URL,
            destination,
            expected_sha256=hashlib.sha256(b"the published tarball").hexdigest(),
            accept_licence=True,
            opener=opener,
        )

    assert _artefacts(tmp_path) == set()


def test_an_interrupted_download_leaves_nothing_at_the_destination(
    tmp_path: Path,
) -> None:
    # spec: adp-005 — the second failure case. A truncated file sitting at the
    # destination path is one a later run reads as complete and filters into a
    # silently short extract. Writing elsewhere and moving only after
    # verification is what makes that unrepresentable.
    class _Interrupting(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            raise ConnectionResetError("connection reset mid-transfer")

    def _open(url: str) -> BinaryIO:
        return _Interrupting()

    destination = tmp_path / "raw" / f"{SNAPSHOT}.csv.tar"

    with pytest.raises(ConnectionResetError):
        download(
            SOURCE_URL,
            destination,
            expected_sha256="0" * 64,
            accept_licence=True,
            opener=_open,
        )

    assert _artefacts(tmp_path) == set()


def test_a_local_file_that_already_matches_is_not_downloaded_again(
    tmp_path: Path,
) -> None:
    # spec: adp-005 — re-fetching ~180 MB on every run is the difference between
    # a rebuild being cheap and being avoided.
    payload = _tar_bytes([_row()])
    destination = tmp_path / "raw" / f"{SNAPSHOT}.csv.tar"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)

    result = download(
        SOURCE_URL,
        destination,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        accept_licence=True,
        opener=_refusing_opener,
    )

    assert result == destination


def test_a_local_file_with_the_wrong_checksum_is_replaced_not_accepted(
    tmp_path: Path,
) -> None:
    # spec: adp-005 — the skip is a checksum match, never mere presence. A
    # leftover truncated file is exactly the case where presence and
    # completeness diverge.
    payload = _tar_bytes([_row()])
    destination = tmp_path / "raw" / f"{SNAPSHOT}.csv.tar"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload[: len(payload) // 2])
    opener, calls = _opener_for(payload)

    download(
        SOURCE_URL,
        destination,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        accept_licence=True,
        opener=opener,
    )

    assert destination.read_bytes() == payload
    assert calls == [SOURCE_URL]


# --------------------------------------------------------------------------
# The source pointer comes from the committed manifest
# --------------------------------------------------------------------------


def test_the_source_url_and_checksum_are_read_from_the_manifest(
    tmp_path: Path,
) -> None:
    # spec: adp-005 — the manifest is what a fresh clone has instead of the
    # data. Hard-coding the URL in the fetcher would let the two drift.
    ref = read_source_ref(_manifest_file(tmp_path, original_sha256="a" * 64))

    assert ref.url == SOURCE_URL
    assert ref.sha256 == "a" * 64
    assert ref.snapshot_hour == "2022-06-27T12:00:00Z"


@pytest.mark.parametrize("missing", ["source_url", "original_sha256"])
def test_a_manifest_without_a_source_pointer_is_rejected(
    tmp_path: Path, missing: str
) -> None:
    # spec: adp-005 — a manifest missing either half cannot be verified against.
    # Downloading anyway would produce an extract nothing could attribute.
    path = _manifest_file(tmp_path, **{missing: None})

    with pytest.raises(ValueError, match=missing):
        read_source_ref(path)


# --------------------------------------------------------------------------
# One command, from a fresh clone to the three artefacts
# --------------------------------------------------------------------------


@pytest.fixture
def fresh_clone(tmp_path: Path) -> Iterator[tuple[Path, bytes]]:
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
    _manifest_file(data_dir, original_sha256=hashlib.sha256(payload).hexdigest())
    yield data_dir, payload


def test_one_run_produces_the_extract_manifest_and_coverage_report(
    fresh_clone: tuple[Path, bytes],
) -> None:
    # spec: adp-005 — the whole point of the item: a clone plus one command is a
    # working corpus, without the licensed bytes ever being committed.
    data_dir, payload = fresh_clone
    opener, _ = _opener_for(payload)

    build_corpus(
        data_dir,
        box=BOX,
        null_sample=0,
        accept_licence=True,
        opener=opener,
        download_date="2026-08-16",
        pseudonymiser=PSEUDONYMISER,
    )

    assert _artefacts(data_dir) == {
        f"raw/{SNAPSHOT}.csv.tar",
        "opensky_extract.parquet",
        "manifest.json",
        "coverage.json",
    }


def test_the_written_manifest_records_the_content_checksum_and_the_box(
    fresh_clone: tuple[Path, bytes],
) -> None:
    # spec: adp-005 — the rewritten manifest is what makes the extract
    # reproducible: same source, same box, same rows out.
    data_dir, payload = fresh_clone
    opener, _ = _opener_for(payload)

    build_corpus(
        data_dir,
        box=BOX,
        null_sample=0,
        accept_licence=True,
        opener=opener,
        download_date="2026-08-16",
        pseudonymiser=PSEUDONYMISER,
    )
    manifest = json.loads((data_dir / "manifest.json").read_text())

    assert manifest["original_sha256"] == hashlib.sha256(payload).hexdigest()
    assert manifest["download_date"] == "2026-08-16"
    assert manifest["bounding_box"]["lat_min"] == 47.0
    assert len(manifest["content_sha256"]) == 64
    assert manifest["attribution"].startswith("The OpenSky Network")


def test_the_coverage_report_is_written_for_the_filtered_rows_only(
    fresh_clone: tuple[Path, bytes],
) -> None:
    # spec: adp-005 — the coverage report exists to accept or reject the box, so
    # measuring it over the unfiltered hour would answer a question nobody asked.
    data_dir, payload = fresh_clone
    opener, _ = _opener_for(payload)

    build_corpus(
        data_dir,
        box=BOX,
        null_sample=0,
        accept_licence=True,
        opener=opener,
        download_date="2026-08-16",
        pseudonymiser=PSEUDONYMISER,
    )
    coverage = json.loads((data_dir / "coverage.json").read_text())

    assert coverage["aircraft"] == 1
    assert coverage["cadence_s"] == 10


def test_a_checksum_mismatch_leaves_no_extract_manifest_or_coverage_report(
    tmp_path: Path,
) -> None:
    # spec: adp-005 — the first failure case in full. Verifying after the filter
    # would still produce all three artefacts, and the manifest beside them would
    # assert a source the bytes did not come from.
    data_dir = tmp_path / "opensky"
    data_dir.mkdir()
    manifest_path = _manifest_file(data_dir, original_sha256="f" * 64)
    before = manifest_path.read_text()
    opener, _ = _opener_for(_tar_bytes([_row()]))

    with pytest.raises(ChecksumMismatchError):
        build_corpus(
            data_dir,
            box=BOX,
            null_sample=0,
            accept_licence=True,
            opener=opener,
            download_date="2026-08-16",
            pseudonymiser=PSEUDONYMISER,
        )

    assert _artefacts(data_dir) == {"manifest.json"}
    assert manifest_path.read_text() == before


def test_the_build_refuses_without_licence_acceptance(
    fresh_clone: tuple[Path, bytes],
) -> None:
    # spec: adp-005 — the gate is on the entrypoint the operator actually runs,
    # not only on the function beneath it.
    data_dir, _ = fresh_clone

    with pytest.raises(LicenceNotAcceptedError):
        build_corpus(
            data_dir,
            box=BOX,
            null_sample=0,
            opener=_refusing_opener,
            download_date="2026-08-16",
            pseudonymiser=PSEUDONYMISER,
        )

    assert _artefacts(data_dir) == {"manifest.json"}
