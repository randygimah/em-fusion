"""Fetch the OpenSky hour and build the corpus from it. Spec: adp-005.

The network half of the corpus tooling, and the only module in it allowed to
open a socket — which is what keeps `extract.py` offline-testable.

    manifest.json  ->  download  ->  verify  ->  extract.py  ->  three artefacts

Three constraints, each because the obvious alternative fails quietly:

* The checksum is verified before the filter runs, not after. Filtering first
  still produces an extract, sitting beside a manifest that cites a source the
  bytes did not come from.
* The download goes to a temporary path and is moved into place only once
  verified. A truncated file left at the destination is one a later run reads
  as complete and filters into a silently short extract.
* Licence acceptance is an explicit act by the operator. The extract is not
  committed precisely so that acceptance belongs to whoever obtains the data;
  fetching on assumed consent would relocate it to whoever wrote this file.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from app.corpus.extract import (
    ATTRIBUTION,
    LICENCE,
    BoundingBox,
    build_manifest,
    content_checksum,
    coverage_report,
    filter_rows,
    read_rows,
    write_parquet,
)

CHUNK_BYTES = 1024 * 1024

# The published hour is one sample per 10 seconds.
DEFAULT_CADENCE_S = 10

Opener = Callable[[str], BinaryIO]


class LicenceNotAcceptedError(RuntimeError):
    """Raised when a fetch is attempted without explicit acceptance."""


class ChecksumMismatchError(RuntimeError):
    """Raised when downloaded bytes are not the source the manifest cites."""


@dataclass(frozen=True)
class SourceRef:
    """Where the corpus came from, as recorded in the committed manifest."""

    url: str
    sha256: str
    snapshot_hour: str


# Excluded from coverage deliberately: executing it would mean downloading
# 180 MB from OpenSky, which is precisely what the suite must never do.
def _urlopen(url: str) -> BinaryIO:  # pragma: no cover
    """The real transport. Injectable so that no test ever reaches it."""
    return urllib.request.urlopen(url)  # type: ignore[no-any-return]


def licence_notice() -> str:
    """The terms and attribution shown at the point of acceptance.

    Acceptance offered without the terms is a consent step with nothing to
    consent to, so this is what the entrypoint prints before it asks.
    """
    return (
        f"{LICENCE['name']}\n"
        f"Governing version: {LICENCE['governing']} — {LICENCE['published_url']}\n"
        f"{LICENCE['note']}\n\n"
        "Downloading this data accepts those terms. The data may not be made "
        "available outside your institute (DLA §3(iii)), aircraft identifiers "
        "must be de-identified before disclosure (§3(i)), and any publication "
        "must cite:\n\n"
        f"{ATTRIBUTION}\n"
    )


def file_sha256(path: Path, chunk_bytes: int = CHUNK_BYTES) -> str:
    """Hash a file in chunks. The published hour is ~180 MB; do not read it
    into memory to check four hundred bits."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def read_source_ref(manifest_path: Path) -> SourceRef:
    """Read the source pointer out of the committed manifest.

    A fresh clone has the manifest and not the data, so the manifest is the
    only authority on what to fetch. Hard-coding the URL here would let the
    two drift apart with nothing to notice.
    """
    manifest = json.loads(Path(manifest_path).read_text())
    for field in ("source_url", "original_sha256"):
        if not manifest.get(field):
            raise ValueError(f"manifest has no {field}: cannot verify a download")

    return SourceRef(
        url=manifest["source_url"],
        sha256=manifest["original_sha256"],
        snapshot_hour=manifest.get("snapshot_hour", ""),
    )


def download(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    accept_licence: bool = False,
    opener: Opener = _urlopen,
    chunk_bytes: int = CHUNK_BYTES,
) -> Path:
    """Fetch `url` to `destination`, verifying it before it lands there.

    Returns the destination. A local file already matching the checksum is
    kept and the transport is never touched — the skip is a checksum match,
    never mere presence, because presence and completeness diverge in exactly
    the truncated-leftover case this guards.
    """
    destination = Path(destination)
    if (
        destination.exists()
        and file_sha256(destination, chunk_bytes) == expected_sha256
    ):
        return destination

    if not accept_licence:
        raise LicenceNotAcceptedError(
            "the OpenSky licence must be accepted explicitly before downloading"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        digest = hashlib.sha256()
        with opener(url) as response, open(partial, "wb") as out:
            while chunk := response.read(chunk_bytes):
                digest.update(chunk)
                out.write(chunk)

        if digest.hexdigest() != expected_sha256:
            raise ChecksumMismatchError(
                f"{url} hashed to {digest.hexdigest()}, manifest records "
                f"{expected_sha256}"
            )
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)

    return destination


def build_corpus(
    data_dir: Path,
    *,
    box: BoundingBox,
    null_sample: int,
    cadence_s: int = DEFAULT_CADENCE_S,
    accept_licence: bool = False,
    opener: Opener = _urlopen,
    download_date: str,
) -> dict[str, Any]:
    """Fresh clone to corpus in one call.

    Reads `data_dir/manifest.json` for the source pointer, downloads and
    verifies, then runs the adp-004 filter over the sealed tarball. Nothing is
    written under `data_dir` until the checksum holds, so an aborted run leaves
    the committed manifest exactly as it found it.
    """
    data_dir = Path(data_dir)
    manifest_path = data_dir / "manifest.json"
    source = read_source_ref(manifest_path)

    raw_path = download(
        source.url,
        data_dir / "raw" / source.url.rsplit("/", 1)[-1],
        source.sha256,
        accept_licence=accept_licence,
        opener=opener,
    )

    kept, stats = filter_rows(read_rows(raw_path), box=box, null_sample=null_sample)
    write_parquet(kept, data_dir / "opensky_extract.parquet")

    manifest = build_manifest(
        source_url=source.url,
        snapshot_hour=source.snapshot_hour,
        download_date=download_date,
        original_sha256=source.sha256,
        content_sha256=content_checksum(kept),
        box=box,
        null_sample=null_sample,
        null_retained=stats.null_retained,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    coverage = coverage_report(kept, cadence_s=cadence_s)
    (data_dir / "coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")

    return manifest
