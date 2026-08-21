"""OpenSky corpus extraction tests.

Every test here proves part of adp-004. None of them touch the real corpus:
the fixtures below build a miniature tarball with the same structure as the
published hourly file, so the suite runs offline and in milliseconds.
"""

import gzip
import io
import socket
import tarfile
from pathlib import Path

import pytest

from app.corpus.extract import (
    BoundingBox,
    build_manifest,
    content_checksum,
    coverage_report,
    filter_rows,
    parquet_schema,
    read_rows,
    validate_manifest,
    write_parquet,
)
from app.dal.pseudonymise import Pseudonymiser

COLUMNS = (
    "time,icao24,lat,lon,velocity,heading,vertrate,callsign,onground,alert,"
    "spi,squawk,baroaltitude,geoaltitude,lastposupdate,lastcontact"
)

# A box over the Benelux/German core, matching the shape of the candidate box.
# A fingerprint, never a seed: the manifest is committed (dal-004).
SEED_FINGERPRINT = Pseudonymiser(seed="a-test-seed").fingerprint()

BOX = BoundingBox(lat_min=47.0, lat_max=55.0, lon_min=3.0, lon_max=15.0)


def _row(
    time: int = 1656331200,
    icao24: str = "4d22ec",
    lat: str = "51.09",
    lon: str = "7.54",
    callsign: str = "CXI27NM ",
) -> str:
    """One CSV line in the published column order."""
    return (
        f"{time},{icao24},{lat},{lon},194.26,135.64,13.32,{callsign},"
        f"False,False,False,2556,5753.1,5951.22,{time - 1}.94,{time}.0"
    )


def _make_tar(path: Path, rows: list[str], name: str = "states_2022-06-27-12") -> Path:
    """Build a tarball shaped like the published one: csv.gz plus LICENSE.txt."""
    body = "\n".join([COLUMNS, *rows]) + "\n"
    gz = gzip.compress(body.encode())
    tar_path = path / f"{name}.csv.tar"
    with tarfile.open(tar_path, "w") as tar:
        for member_name, payload in (
            (f"{name}.csv.gz", gz),
            ("LICENSE.txt", b"General Terms of Use & Data License Agreement\n"),
            ("README.txt", b"OpenSky Data Sample\n"),
        ):
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return tar_path


# --------------------------------------------------------------------------
# Reading: the archive stays sealed
# --------------------------------------------------------------------------


def test_read_rows_streams_from_the_tar_without_unpacking_it(tmp_path: Path) -> None:
    # spec: adp-004 — the manifest checksums the tar as published, so unpacking
    # would leave the artefact on disk no longer the one that was verified.
    tar_path = _make_tar(tmp_path, [_row(), _row(time=1656331210)])

    rows = list(read_rows(tar_path))

    assert len(rows) == 2
    assert [p.name for p in tmp_path.iterdir()] == [tar_path.name]


def test_read_rows_preserves_source_values_verbatim(tmp_path: Path) -> None:
    # spec: adp-004 — callsigns are space-padded to 8 characters in the source.
    # Trimming here would silently change the bytes the checksum covers.
    tar_path = _make_tar(tmp_path, [_row(callsign="KLM30Q  ")])

    row = next(iter(read_rows(tar_path)))

    assert row["callsign"] == "KLM30Q  "
    assert row["onground"] == "False"


def test_read_rows_ignores_the_licence_and_readme_members(tmp_path: Path) -> None:
    # spec: adp-004 — the tar carries three members. Treating LICENSE.txt as
    # data would inject its text into the observation stream.
    tar_path = _make_tar(tmp_path, [_row()])

    rows = list(read_rows(tar_path))

    assert len(rows) == 1
    assert rows[0]["icao24"] == "4d22ec"


# --------------------------------------------------------------------------
# Filtering: the bounding box
# --------------------------------------------------------------------------


def test_rows_inside_the_box_are_kept_and_rows_outside_are_dropped() -> None:
    # spec: adp-004
    rows = [
        {"icao24": "aaa111", "lat": "51.09", "lon": "7.54", "time": "1656331200"},
        {"icao24": "bbb222", "lat": "37.89", "lon": "-88.93", "time": "1656331200"},
    ]

    kept, stats = filter_rows(rows, box=BOX, null_sample=0)

    assert [r["icao24"] for r in kept] == ["aaa111"]
    assert stats.in_box == 1
    assert stats.out_of_box == 1


def test_a_row_on_the_box_boundary_is_kept() -> None:
    # spec: adp-004 — an exclusive bound silently shrinks the region, and the
    # coverage check would then be measuring a different box than the manifest
    # records.
    rows = [{"icao24": "aaa111", "lat": "47.0", "lon": "3.0", "time": "1"}]

    kept, _ = filter_rows(rows, box=BOX, null_sample=0)

    assert len(kept) == 1


# --------------------------------------------------------------------------
# Filtering: deliberate retention of null-position rows
# --------------------------------------------------------------------------


def test_null_position_rows_are_retained_up_to_the_configured_bound() -> None:
    # spec: adp-004 — a bounding-box test cannot be applied to a null
    # coordinate, so without deliberate retention dal-002's quarantine path has
    # no real input and AC-02 is demonstrable only by fixture.
    rows = [
        {"icao24": f"nul{i:03d}", "lat": "", "lon": "", "time": str(i)}
        for i in range(5)
    ]

    kept, stats = filter_rows(rows, box=BOX, null_sample=2)

    assert stats.null_retained == 2
    assert len([r for r in kept if not r["lat"]]) == 2


def test_null_position_retention_takes_the_first_rows_in_file_order() -> None:
    # spec: adp-004 — file order rather than a seeded sample, so retention
    # needs no seed of its own and stays deterministic for a given raw file.
    rows = [
        {"icao24": f"nul{i:03d}", "lat": "", "lon": "", "time": str(i)}
        for i in range(5)
    ]

    kept, _ = filter_rows(rows, box=BOX, null_sample=3)

    assert [r["icao24"] for r in kept] == ["nul000", "nul001", "nul002"]


def test_null_position_rows_do_not_count_towards_the_in_box_total() -> None:
    # spec: adp-004 — a row with no position is not evidence of coverage, and
    # counting it as in-box would inflate the density the box is chosen on.
    rows = [
        {"icao24": "aaa111", "lat": "51.09", "lon": "7.54", "time": "1"},
        {"icao24": "nul001", "lat": "", "lon": "", "time": "2"},
    ]

    _, stats = filter_rows(rows, box=BOX, null_sample=1)

    assert stats.in_box == 1
    assert stats.null_retained == 1


def test_an_extract_never_drops_every_available_null_position_row() -> None:
    # spec: adp-004 — the third failure case. An extract with no null-position
    # rows at all passes a naive review while removing the only real-data input
    # dal-002 has.
    rows = [
        {"icao24": "aaa111", "lat": "51.09", "lon": "7.54", "time": "1"},
        {"icao24": "nul001", "lat": "", "lon": "", "time": "2"},
    ]

    kept, stats = filter_rows(rows, box=BOX, null_sample=500)

    assert stats.null_available == 1
    assert stats.null_retained == 1
    assert any(not r["lat"] for r in kept)


def test_a_row_missing_only_one_coordinate_counts_as_null_position() -> None:
    # spec: adp-004 — a lone latitude cannot be placed, and treating it as
    # positioned would put an observation at a default coordinate.
    rows = [{"icao24": "aaa111", "lat": "51.09", "lon": "", "time": "1"}]

    _, stats = filter_rows(rows, box=BOX, null_sample=1)

    assert stats.null_available == 1
    assert stats.in_box == 0


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_filtering_the_same_input_twice_yields_the_same_content_checksum() -> None:
    # spec: adp-004 — verified by content checksum rather than byte equality,
    # since Parquet writers embed non-deterministic metadata.
    rows = [
        {"icao24": "aaa111", "lat": "51.09", "lon": "7.54", "time": "1"},
        {"icao24": "nul001", "lat": "", "lon": "", "time": "2"},
    ]

    first, _ = filter_rows(rows, box=BOX, null_sample=1)
    second, _ = filter_rows(rows, box=BOX, null_sample=1)

    assert content_checksum(first) == content_checksum(second)


def test_a_changed_row_changes_the_content_checksum() -> None:
    # spec: adp-004 — a checksum that does not move when the data moves proves
    # nothing about reproducibility.
    base = [{"icao24": "aaa111", "lat": "51.09", "lon": "7.54", "time": "1"}]
    changed = [{"icao24": "aaa111", "lat": "51.10", "lon": "7.54", "time": "1"}]

    assert content_checksum(base) != content_checksum(changed)


# --------------------------------------------------------------------------
# Typing: the reason Parquet was kept
# --------------------------------------------------------------------------


def test_parquet_schema_declares_icao24_and_callsign_as_strings() -> None:
    # spec: adp-004 — the schema lives in the artefact rather than in code, so
    # a reader cannot infer it differently.
    schema = parquet_schema()

    assert str(schema.field("icao24").type) == "string"
    assert str(schema.field("callsign").type) == "string"


def test_a_leading_zero_icao24_survives_the_parquet_round_trip(tmp_path: Path) -> None:
    # spec: adp-004 — 14,781 rows in the downloaded hour carry an all-digit
    # icao24 beginning with a zero. Inferred as an integer, '004321' becomes
    # 4321: the leading zeros are gone, two airframes can collide onto one
    # identifier, and no error is raised. icao24 is the key every
    # track-continuity rule groups by, so this corrupts detection silently.
    import pyarrow.parquet as pq

    rows = [{"icao24": "004321", "lat": "51.09", "lon": "7.54", "time": "1"}]
    out = tmp_path / "opensky_extract.parquet"

    write_parquet(rows, out)
    table = pq.read_table(out)

    assert table.column("icao24").to_pylist() == ["004321"]


def test_a_retained_null_position_row_keeps_null_coordinates(tmp_path: Path) -> None:
    # spec: adp-004 — the retained sample exists to feed dal-002. Writing its
    # missing coordinates as 0.0 would place the row off West Africa instead of
    # marking it unplaceable, which is the default-coordinate failure adp-001
    # names.
    import pyarrow.parquet as pq

    rows = [{"icao24": "nul001", "lat": "", "lon": "", "time": "1"}]
    out = tmp_path / "opensky_extract.parquet"

    write_parquet(rows, out)
    table = pq.read_table(out)

    assert table.column("lat").to_pylist() == [None]
    assert table.column("lon").to_pylist() == [None]


def test_source_booleans_round_trip_as_booleans(tmp_path: Path) -> None:
    # spec: adp-004 — the source writes Python-style 'False'/'True'. Left as
    # strings, every value is truthy and onground stops meaning anything.
    import pyarrow.parquet as pq

    rows = [{"icao24": "aaa111", "onground": "True", "alert": "False", "time": "1"}]
    out = tmp_path / "opensky_extract.parquet"

    write_parquet(rows, out)
    table = pq.read_table(out)

    assert table.column("onground").to_pylist() == [True]
    assert table.column("alert").to_pylist() == [False]


def test_a_tar_without_a_csv_member_is_rejected(tmp_path: Path) -> None:
    # spec: adp-004 — a tar that carries only the licence and readme is not a
    # corpus, and must say so rather than yielding zero rows silently.
    tar_path = tmp_path / "empty.csv.tar"
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo("LICENSE.txt")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"none"))

    with pytest.raises(ValueError, match="csv.gz"):
        list(read_rows(tar_path))


# --------------------------------------------------------------------------
# Offline guarantee
# --------------------------------------------------------------------------


def test_filtering_performs_no_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: adp-004 — the first failure case. A filter that reaches the network
    # when the raw file is missing reintroduces the dependency the archive
    # exists to remove, and makes the step untestable offline.
    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the extraction step must not open a socket")

    monkeypatch.setattr(socket, "socket", _refuse)
    tar_path = _make_tar(tmp_path, [_row()])

    kept, _ = filter_rows(read_rows(tar_path), box=BOX, null_sample=0)

    assert len(kept) == 1


def test_a_missing_raw_file_raises_rather_than_downloading(tmp_path: Path) -> None:
    # spec: adp-004 — the absent file must be a loud failure, not a silent
    # fetch.
    with pytest.raises(FileNotFoundError):
        list(read_rows(tmp_path / "absent.csv.tar"))


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------


def test_manifest_records_provenance_and_licence_fields() -> None:
    # spec: adp-004 — the terms as published on the download date cannot be
    # reconstructed later, and the shipped LICENSE.txt is not the operative one.
    manifest = build_manifest(
        source_url="https://s3.opensky-network.org/data-samples/states/"
        "2022-06-27/12/states_2022-06-27-12.csv.tar",
        snapshot_hour="2022-06-27T12:00:00Z",
        download_date="2026-08-13",
        original_sha256="6e0d2278",
        content_sha256="abc123",
        box=BOX,
        null_sample=500,
        null_retained=500,
        pseudonym_seed_sha256=SEED_FINGERPRINT,
    )

    for key in (
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
    ):
        assert key in manifest, f"manifest is missing {key}"


def test_manifest_records_both_licence_versions_and_which_governs() -> None:
    # spec: adp-004 — the LICENSE.txt shipped in the tarball is dated 2017 and
    # is more permissive than the published terms, which §2(iii) makes
    # operative. A reader consulting only the shipped file concludes wrongly.
    manifest = build_manifest(
        source_url="https://example.invalid/x.csv.tar",
        snapshot_hour="2022-06-27T12:00:00Z",
        download_date="2026-08-13",
        original_sha256="6e0d2278",
        content_sha256="abc123",
        box=BOX,
        null_sample=500,
        null_retained=500,
        pseudonym_seed_sha256=SEED_FINGERPRINT,
    )

    assert manifest["licence"]["governing"] == "published"
    assert "shipped_sha256" in manifest["licence"]
    assert "published_url" in manifest["licence"]
    assert "retrieved" in manifest["licence"]


@pytest.mark.parametrize(
    "missing", ["original_sha256", "licence", "attribution", "pseudonym_seed_sha256"]
)
def test_a_manifest_missing_a_required_field_is_rejected(missing: str) -> None:
    # spec: adp-004 — the second failure case. Without these the artefact is
    # neither reproducible nor attributable.
    manifest = build_manifest(
        source_url="https://example.invalid/x.csv.tar",
        snapshot_hour="2022-06-27T12:00:00Z",
        download_date="2026-08-13",
        original_sha256="6e0d2278",
        content_sha256="abc123",
        box=BOX,
        null_sample=500,
        null_retained=500,
        pseudonym_seed_sha256=SEED_FINGERPRINT,
    )
    del manifest[missing]

    with pytest.raises(ValueError, match=missing):
        validate_manifest(manifest)


# --------------------------------------------------------------------------
# Coverage report
# --------------------------------------------------------------------------


def test_coverage_report_measures_gaps_per_aircraft() -> None:
    # spec: adp-004 — the report exists to decide whether natural gaps overlap
    # the durations aircraft-coverage-gap will inject.
    rows = [
        {"icao24": "aaa111", "lat": "51.0", "lon": "7.0", "time": "0"},
        {"icao24": "aaa111", "lat": "51.0", "lon": "7.0", "time": "10"},
        {"icao24": "aaa111", "lat": "51.0", "lon": "7.0", "time": "90"},
    ]

    report = coverage_report(rows, cadence_s=10)

    assert report["max_gap_s"] == 80
    assert report["aircraft"] == 1


def test_coverage_report_excludes_null_position_rows() -> None:
    # spec: adp-004 — a row with no position is not a coverage gap, and
    # counting the retained sample as one would invent gaps that are artefacts
    # of the retention decision.
    rows = [
        {"icao24": "aaa111", "lat": "51.0", "lon": "7.0", "time": "0"},
        {"icao24": "aaa111", "lat": "", "lon": "", "time": "10"},
        {"icao24": "aaa111", "lat": "51.0", "lon": "7.0", "time": "20"},
    ]

    report = coverage_report(rows, cadence_s=10)

    assert report["max_gap_s"] == 20


def test_coverage_report_reports_the_gap_distribution_not_just_the_maximum() -> None:
    # spec: adp-004 — the acceptance decision compares a distribution against
    # the injected durations. A single maximum cannot support that judgement,
    # and one outlying aircraft would condemn an otherwise dense box.
    rows = [
        {"icao24": "aaa111", "lat": "51.0", "lon": "7.0", "time": str(t)}
        for t in (0, 10, 20, 30)
    ]

    report = coverage_report(rows, cadence_s=10)

    assert "gap_percentiles" in report
    assert report["clean_cadence_fraction"] == pytest.approx(1.0)
