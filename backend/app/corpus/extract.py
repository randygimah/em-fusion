"""Turn one downloaded OpenSky hour into the local corpus. Spec: adp-004.

This module is the tool; `opensky_extract.parquet` is the artefact it writes.
Run by hand when the corpus is built — not on the request path. `adp-001`
replays the extract; observations are served from PostGIS.

    states_2022-06-27-12.csv.tar  ->  opensky_extract.parquet  (gitignored)
                                      manifest.json            (committed)
                                      coverage.json            (committed)

A slice, not a re-encoding: ~255k of the hour's 2.86M rows survive the box.

Four constraints, each because the obvious alternative fails quietly:

* No network. Downloading is a separate manual step, so this stays testable
  offline and cannot reintroduce the dependency the archive removes.
* The tar is never unpacked — the manifest checksums it as published, and
  LICENSE.txt travels inside it.
* `icao24` and `callsign` stay strings. Inferred as an integer, `004321`
  becomes `4321`: leading zeros gone, airframes colliding, no error raised.
  Parquet is used for its in-file schema, not for compression.
* Rows with a null lat or lon are kept up to a bound. A box cannot be tested
  against a null, so a pure spatial filter would leave `dal-002`'s quarantine
  path with no real input. Such rows can only reach quarantine, never a
  canonical observation.

Real identifiers stay here; the licence restricts disclosure, not local use.
Pseudonymisation happens downstream at the DAL (`dal-004`).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import tarfile
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

# The published column order. squawk and icao24 are strings for the same
# reason: both are codes whose leading zeros carry meaning.
SCHEMA_FIELDS: tuple[tuple[str, pa.DataType], ...] = (
    ("time", pa.int64()),
    ("icao24", pa.string()),
    ("lat", pa.float64()),
    ("lon", pa.float64()),
    ("velocity", pa.float64()),
    ("heading", pa.float64()),
    ("vertrate", pa.float64()),
    ("callsign", pa.string()),
    ("onground", pa.bool_()),
    ("alert", pa.bool_()),
    ("spi", pa.bool_()),
    ("squawk", pa.string()),
    ("baroaltitude", pa.float64()),
    ("geoaltitude", pa.float64()),
    ("lastposupdate", pa.float64()),
    ("lastcontact", pa.float64()),
)

# Captured at download time. The tarball ships a LICENSE.txt dated 2017-08-24
# that is more permissive than the terms now published; §2(iii) makes the
# published version operative, so both are recorded and one is named as
# governing rather than leaving a reader to pick.
LICENCE: dict[str, str] = {
    "name": "OpenSky Network General Terms of Use & Data License Agreement",
    "governing": "published",
    "published_url": "https://opensky-network.org/about/terms-of-use",
    "retrieved": "2026-08-13",
    "shipped_sha256": (
        "d4ea34f0786652cf6252da10660b1490cc45c181254a1705f0661a48d14a3ec2"
    ),
    "shipped_dated": "2017-08-24",
    "note": (
        "The LICENSE.txt shipped inside the tarball permits commercial internal "
        "testing and government purposes; the published terms do not. §2(iii) "
        "makes the published terms operative."
    ),
}

# Required by §4(i): a publication must cite one of these two forms.
ATTRIBUTION = (
    "The OpenSky Network, http://www.opensky-network.org — or Schäfer, M., "
    "Strohmeier, M., Lenders, V., Martinovic, I. and Wilhelm, M. (2014) "
    "'Bringing up OpenSky: A large-scale ADS-B sensor network for research', "
    "ACM/IEEE International Conference on Information Processing in Sensor "
    "Networks (IPSN), April 2014."
)

REQUIRED_MANIFEST_FIELDS: tuple[str, ...] = (
    "source_url",
    "snapshot_hour",
    "download_date",
    "original_sha256",
    "content_sha256",
    "licence",
    "attribution",
    "bounding_box",
    "null_sample",
    "null_retained",
)


@dataclass(frozen=True)
class BoundingBox:
    """A geographic box. Bounds are inclusive: a row exactly on the edge is
    kept, so the region filtered matches the region the manifest records."""

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def contains(self, lat: float, lon: float) -> bool:
        return (
            self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max
        )


@dataclass(frozen=True)
class ExtractStats:
    """What the filter saw. `null_available` is the count in the source;
    `null_retained` is how many of them the bound let through."""

    in_box: int
    out_of_box: int
    null_available: int
    null_retained: int


def read_rows(tar_path: Path) -> Iterator[dict[str, str]]:
    """Stream rows from the sealed tarball.

    The archive is never unpacked and never partially written to disk, so the
    file on disk stays the one the manifest checksummed. LICENSE.txt and
    README.txt travel in the same tar and are skipped.
    """
    path = Path(tar_path)
    if not path.exists():
        raise FileNotFoundError(f"raw OpenSky file not found: {path}")

    with tarfile.open(path) as tar:
        member = next(
            (m for m in tar.getmembers() if m.name.endswith(".csv.gz")),
            None,
        )
        if member is None:
            raise ValueError(f"no .csv.gz member in {path}")

        handle = tar.extractfile(member)
        if handle is None:  # pragma: no cover - only for non-regular members
            raise ValueError(f"could not read {member.name} from {path}")

        with gzip.open(handle, "rt", newline="") as text:
            yield from csv.DictReader(text)


def filter_rows(
    rows: Iterable[dict[str, str]],
    box: BoundingBox,
    null_sample: int,
) -> tuple[list[dict[str, str]], ExtractStats]:
    """Apply the bounding box, keeping a bounded sample of unplaceable rows.

    A row with a missing lat or lon cannot be tested against the box at all, so
    it is neither in nor out — it is counted separately and the first
    `null_sample` of them are kept in file order. That ordering is why this
    needs no seed: it is already deterministic for a given raw file.
    """
    kept: list[dict[str, str]] = []
    in_box = out_of_box = null_available = null_retained = 0

    for row in rows:
        lat, lon = row.get("lat", ""), row.get("lon", "")
        if not lat or not lon:
            null_available += 1
            if null_retained < null_sample:
                kept.append(row)
                null_retained += 1
        elif box.contains(float(lat), float(lon)):
            kept.append(row)
            in_box += 1
        else:
            out_of_box += 1

    return kept, ExtractStats(in_box, out_of_box, null_available, null_retained)


def content_checksum(rows: Iterable[Mapping[str, str]]) -> str:
    """Hash row content, not file bytes.

    Parquet writers embed timestamps and library versions, so two runs over
    identical data produce different files. This checksum is what the spec's
    determinism constraint is actually verified against.
    """
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def parquet_schema() -> pa.Schema:
    """The schema carried inside the artefact, so no reader can infer it."""
    return pa.schema(SCHEMA_FIELDS)


def _coerce(value: str | None, field_type: pa.DataType) -> Any:
    """One CSV cell to its typed value. Absent and empty both become null,
    except for strings, where an empty callsign is a real observation."""
    if value is None:
        return None
    if pa.types.is_string(field_type):
        return value
    if value == "":
        return None
    if pa.types.is_boolean(field_type):
        return value.strip().lower() == "true"
    if pa.types.is_integer(field_type):
        return int(float(value))
    return float(value)


def write_parquet(rows: Iterable[Mapping[str, str]], path: Path) -> None:
    """Write the extract with an explicit schema. Never infer types here."""
    columns: dict[str, list[Any]] = {name: [] for name, _ in SCHEMA_FIELDS}
    for row in rows:
        for name, field_type in SCHEMA_FIELDS:
            columns[name].append(_coerce(row.get(name), field_type))

    pq.write_table(pa.Table.from_pydict(columns, schema=parquet_schema()), path)


def _percentile(ordered: list[int], pct: float) -> int:
    """Nearest-rank percentile. Integer seconds in, integer seconds out."""
    if not ordered:
        return 0
    index = max(0, math.ceil(pct / 100 * len(ordered)) - 1)
    return ordered[index]


def coverage_report(
    rows: Iterable[Mapping[str, str]], cadence_s: int
) -> dict[str, Any]:
    """Measure natural gaps, so the bounding box can be accepted or rejected.

    Computed over positioned rows only: a row with no position is not a
    coverage gap, and counting the retained null sample as one would invent
    gaps that are artefacts of the retention decision.

    The distribution matters more than the maximum. A single outlying aircraft
    would condemn an otherwise dense box, so the acceptance judgement is made
    against percentiles and the clean-cadence fraction.
    """
    times_by_aircraft: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        if not row.get("lat") or not row.get("lon"):
            continue
        times_by_aircraft[row["icao24"]].append(int(float(row["time"])))

    gaps: list[int] = []
    for times in times_by_aircraft.values():
        times.sort()
        gaps.extend(later - earlier for earlier, later in zip(times, times[1:]))

    ordered = sorted(gaps)
    clean = sum(1 for gap in ordered if gap <= cadence_s)

    return {
        "cadence_s": cadence_s,
        "aircraft": len(times_by_aircraft),
        "gaps": len(ordered),
        "max_gap_s": ordered[-1] if ordered else 0,
        "gap_percentiles": {
            "p50": _percentile(ordered, 50),
            "p90": _percentile(ordered, 90),
            "p99": _percentile(ordered, 99),
        },
        "clean_cadence_fraction": (clean / len(ordered)) if ordered else 1.0,
    }


def build_manifest(
    source_url: str,
    snapshot_hour: str,
    download_date: str,
    original_sha256: str,
    content_sha256: str,
    box: BoundingBox,
    null_sample: int,
    null_retained: int,
) -> dict[str, Any]:
    """Assemble the committed record of where the extract came from.

    Licence and attribution are module constants rather than arguments: they
    are a property of the source, and a caller that has to supply them is a
    caller that can forget them.
    """
    return {
        "source_url": source_url,
        "snapshot_hour": snapshot_hour,
        "download_date": download_date,
        "original_sha256": original_sha256,
        "content_sha256": content_sha256,
        "licence": dict(LICENCE),
        "attribution": ATTRIBUTION,
        "bounding_box": asdict(box),
        "null_sample": null_sample,
        "null_retained": null_retained,
    }


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Raise if the manifest could not support a reproduction or a citation."""
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            raise ValueError(f"manifest is missing required field: {field}")
