"""The OpenSky replay adapter. Spec: adp-001.

The adapter's whole job is dialect translation: Parquet rows in, source
records out. It converts nothing into a canonical observation, judges no row
malformed, and persists nothing -- `validate_record` and `ingest_batch` do
all three, and the tests below assert the split rather than assuming it.

Fixtures are written through `app.corpus.extract.write_parquet` so they carry
the same in-file schema as the real artefact. That import is deliberate and
belongs to the *test*: `test_the_adapter_does_not_import_the_corpus_tool`
asserts the adapter itself has no such dependency.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.adapters import opensky
from app.adapters.opensky import Window, available_window, read_window, replay_window
from app.corpus.extract import write_parquet
from app.dal.models import DataMode, ObservationType, SourceType
from app.dal.pseudonymise import Pseudonymiser
from app.dal.validation import IngestContext
from tests.fakes import InMemoryObservationRepository

HOUR_START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
EPOCH_START = int(HOUR_START.timestamp())

CONTEXT = IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=7)
PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")

MANIFEST: dict[str, Any] = {"snapshot_hour": "2022-06-27T12:00:00Z"}


def _row(offset_s: int, **overrides: Any) -> dict[str, str]:
    """One extract row as CSV cells, the shape `write_parquet` coerces.

    Defaults describe a well-formed airborne aircraft; a test overrides only
    the field it is about, and `""` is how the source spells a null.
    """
    row = {
        "time": str(EPOCH_START + offset_s),
        "icao24": "3c6444",
        "lat": "51.09",
        "lon": "7.54",
        "velocity": "194.26",
        "heading": "135.64",
        "vertrate": "13.32",
        "callsign": "DLH8AT  ",
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


@pytest.fixture
def extract(tmp_path: Path) -> Path:
    """A four-frame extract at the 10-second cadence, one row per frame."""
    path = tmp_path / "opensky_extract.parquet"
    write_parquet([_row(0), _row(10), _row(20), _row(30)], path)
    return path


def _write(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "opensky_extract.parquet"
    write_parquet(rows, path)
    return path


def _window(from_s: int, to_s: int) -> Window:
    return Window(
        start=HOUR_START + timedelta(seconds=from_s),
        end=HOUR_START + timedelta(seconds=to_s),
    )


# --- The reader emits source records, not canonical observations -----------


def test_the_reader_emits_records_in_the_dal_source_record_shape(
    extract: Path,
) -> None:
    # spec: adp-001
    records = list(read_window(extract, _window(0, 10)))

    assert len(records) == 1
    record = records[0]
    assert record["source_id"] == opensky.SOURCE_ID
    assert record["source_type"] is SourceType.OPENSKY
    assert record["observation_type"] is ObservationType.TRACK
    assert record["timestamp"] == HOUR_START
    assert record["location"] == {"lat": 51.09, "lon": 7.54}


def test_the_reader_carries_no_provenance(extract: Path) -> None:
    """Provenance is the DAL's (`dal-003`); a record supplying its own is
    rejected outright, so emitting one would fail every row."""
    # spec: adp-001
    record = next(read_window(extract, _window(0, 10)))

    assert "provenance" not in record
    assert "data_mode" not in record
    assert "scenario_run_id" not in record


def test_the_reader_emits_real_identifiers_rather_than_pseudonyms(
    extract: Path,
) -> None:
    """The precondition for `dal-004`, not a breach of it: the DAL can only
    substitute an identifier that reaches it. An adapter supplying a ready-made
    `aircraft_id` would be the pseudonymiser, which is the defect `dal-001`'s
    original fixtures carried."""
    # spec: adp-001
    payload = next(read_window(extract, _window(0, 10)))["payload"]

    assert payload["icao24"] == "3c6444"
    assert payload["callsign"] == "DLH8AT  "
    assert "aircraft_id" not in payload
    assert "flight_id" not in payload


# --- The window is half-open, and empty means empty ------------------------


def test_the_window_includes_its_start_and_excludes_its_end(
    extract: Path,
) -> None:
    """Half-open, so a runner stepping contiguous windows sees each frame
    exactly once rather than double-counting the boundary."""
    # spec: adp-001
    records = list(read_window(extract, _window(0, 20)))

    offsets = [int(r["timestamp"].timestamp()) - EPOCH_START for r in records]
    assert offsets == [0, 10]


def test_an_empty_window_yields_nothing(extract: Path) -> None:
    """The fifth failure case -- the default-to-all bug."""
    # spec: adp-001
    assert list(read_window(extract, _window(10, 10))) == []


def test_an_inverted_window_yields_nothing(extract: Path) -> None:
    # spec: adp-001
    assert list(read_window(extract, _window(30, 0))) == []


def test_a_window_beyond_the_extract_yields_nothing(extract: Path) -> None:
    # spec: adp-001
    assert list(read_window(extract, _window(3000, 3600))) == []


def test_records_are_yielded_in_ascending_time_order(tmp_path: Path) -> None:
    """Continuity and inter-sample gap rules read samples in sequence, so an
    out-of-order emission would manufacture negative gaps."""
    # spec: adp-001
    path = _write(tmp_path, [_row(30), _row(0), _row(20), _row(10)])

    offsets = [
        int(r["timestamp"].timestamp()) - EPOCH_START
        for r in read_window(path, _window(0, 40))
    ]
    assert offsets == sorted(offsets)


def test_the_reader_is_lazy(extract: Path) -> None:
    """`adp-001` requires the window yielded rather than materialised: the
    extract is 133,634 rows and a caller asking for the hour should not force
    it into memory."""
    # spec: adp-001
    result = read_window(extract, _window(0, 40))

    assert isinstance(result, Iterator)
    assert not isinstance(result, (list, tuple))


# --- Measured fields are measured, never defaulted -------------------------


def test_position_staleness_is_the_measured_delta_from_lastposupdate(
    tmp_path: Path,
) -> None:
    # spec: adp-001
    path = _write(tmp_path, [_row(10, lastposupdate=str(EPOCH_START + 4))])

    payload = next(read_window(path, _window(0, 20)))["payload"]
    assert payload["position_staleness_s"] == pytest.approx(6.0)


def test_a_row_without_lastposupdate_does_not_default_staleness_to_zero(
    tmp_path: Path,
) -> None:
    """The fourth failure case. Zero asserts a perfectly fresh position for a
    row that has none, which suppresses the very rule the field feeds. The
    corpus never exercises this -- `lastposupdate` is null on exactly the 500
    null-position rows -- so it is proven by fixture."""
    # spec: adp-001
    path = _write(tmp_path, [_row(10, lastposupdate="")])

    payload = next(read_window(path, _window(0, 20)))["payload"]
    assert payload["position_staleness_s"] != 0
    assert payload["position_staleness_s"] is None


def test_altitude_takes_the_barometric_reading(tmp_path: Path) -> None:
    """One consistent reference across the fleet, and not the GNSS-derived
    field whose disruption the project injects."""
    # spec: adp-001
    path = _write(tmp_path, [_row(10, baroaltitude="5753.1", geoaltitude="5951.22")])

    payload = next(read_window(path, _window(0, 20)))["payload"]
    assert payload["altitude_m"] == pytest.approx(5753.1)


def test_altitude_falls_back_to_geoaltitude_when_barometric_is_absent(
    tmp_path: Path,
) -> None:
    """Fires on zero rows of the current corpus -- the null sets nest -- and
    is retained against a re-filter over a different box."""
    # spec: adp-001
    path = _write(tmp_path, [_row(10, baroaltitude="", geoaltitude="5951.22")])

    payload = next(read_window(path, _window(0, 20)))["payload"]
    assert payload["altitude_m"] == pytest.approx(5951.22)


def test_a_row_with_neither_altitude_yields_none_not_zero(
    tmp_path: Path,
) -> None:
    """22.7 per cent of positioned rows. Zero would place a cruising aircraft
    at sea level; carrying the previous sample forward would manufacture
    continuity the source never reported."""
    # spec: adp-001
    path = _write(tmp_path, [_row(0), _row(10, baroaltitude="", geoaltitude="")])

    records = list(read_window(path, _window(0, 20)))
    assert records[1]["payload"]["altitude_m"] is None


# --- The adapter judges nothing --------------------------------------------


def test_a_null_position_row_is_emitted_rather_than_filtered(
    tmp_path: Path,
) -> None:
    """The third failure case. `adp-004` retained 500 of these so `dal-002`'s
    quarantine path has real input; an adapter that dropped them would satisfy
    the first failure case by never exercising it."""
    # spec: adp-001
    path = _write(tmp_path, [_row(0), _row(10, lat="", lon="")])

    records = list(read_window(path, _window(0, 20)))
    assert len(records) == 2


# --- Reads from file, never from the network -------------------------------


def test_the_reader_never_opens_a_socket(
    extract: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second failure case: an adapter that fetches when the extract is
    missing silently reintroduces the dependency the archive removes."""

    # spec: adp-001
    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the replay adapter must not open a socket")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)

    assert list(read_window(extract, _window(0, 40)))


def test_a_missing_extract_raises_and_names_the_build_command(
    tmp_path: Path,
) -> None:
    """It must fail loudly rather than fetching, and the diagnostic has to
    point at `adp-006` -- the reader cannot rebuild the corpus itself."""
    # spec: adp-001
    with pytest.raises(FileNotFoundError) as excinfo:
        list(read_window(tmp_path / "absent.parquet", _window(0, 40)))

    assert "app.corpus.build" in str(excinfo.value)


def test_the_adapter_does_not_import_the_corpus_tool() -> None:
    """The consumer of the artefact must not depend on the build-time tool
    that downloads and filters it."""
    # spec: adp-001
    source = Path(opensky.__file__).read_text()

    assert "app.corpus" not in source


# --- The manifest supplies the span, and nothing else ----------------------


def test_available_window_is_derived_from_the_manifest_snapshot_hour() -> None:
    """The eighth failure case is deriving this by scanning rows, which reads
    the whole extract to answer what the manifest already records."""
    # spec: adp-001
    window = available_window(MANIFEST)

    assert window.start == HOUR_START
    assert window.end == HOUR_START + timedelta(hours=1)


def test_available_window_needs_no_extract() -> None:
    """It takes the manifest alone, so it cannot be scanning the artefact."""
    # spec: adp-001
    assert available_window(MANIFEST).start == HOUR_START


def test_a_manifest_without_a_snapshot_hour_fails_loudly() -> None:
    # spec: adp-001
    with pytest.raises(KeyError):
        available_window({})


# --- Wiring: the DAL does the converting and the quarantining --------------


def test_replay_window_persists_through_the_dal(extract: Path) -> None:
    # spec: adp-001
    repository = InMemoryObservationRepository()

    result = replay_window(extract, _window(0, 40), CONTEXT, repository, PSEUDONYMISER)

    assert result.accepted == 4
    assert result.quarantined == 0
    assert len(repository.observations) == 4


def test_a_null_position_row_reaches_quarantine_not_an_observation(
    tmp_path: Path,
) -> None:
    """The first failure case, end to end: the adapter emits the row, the DAL
    rejects it, and nothing lands at a default coordinate."""
    # spec: adp-001
    path = _write(tmp_path, [_row(0), _row(10, lat="", lon="")])
    repository = InMemoryObservationRepository()

    result = replay_window(path, _window(0, 20), CONTEXT, repository, PSEUDONYMISER)

    assert (result.accepted, result.quarantined) == (1, 1)
    assert len(repository.observations) == 1
    assert repository.quarantined[0].scenario_run_id == 7


def test_the_replayed_observation_carries_provenance_from_the_context(
    extract: Path,
) -> None:
    """`dal-003` at the far end of the adapter."""
    # spec: adp-001
    repository = InMemoryObservationRepository()

    replay_window(extract, _window(0, 10), CONTEXT, repository, PSEUDONYMISER)

    provenance = repository.observations[0].provenance
    assert provenance.source_id == opensky.SOURCE_ID
    assert provenance.source_type is SourceType.OPENSKY
    assert provenance.data_mode is DataMode.REPLAYED
    assert provenance.scenario_run_id == 7


def test_the_replayed_observation_carries_a_pseudonym(extract: Path) -> None:
    """`dal-004` at the far end. The adapter handed over `3c6444`; nothing
    downstream of the DAL may still hold it."""
    # spec: adp-001
    repository = InMemoryObservationRepository()

    replay_window(extract, _window(0, 10), CONTEXT, repository, PSEUDONYMISER)

    payload = repository.observations[0].payload
    assert payload.aircraft_id != "3c6444"
    assert "3c6444" not in repr(repository.observations[0])


def test_replay_window_receives_its_repository_rather_than_importing_one(
    extract: Path,
) -> None:
    """The seventh failure case. Two repositories, two runs, no shared state:
    only possible if the caller supplies it."""
    # spec: adp-001
    first, second = (
        InMemoryObservationRepository(),
        InMemoryObservationRepository(),
    )

    replay_window(extract, _window(0, 10), CONTEXT, first, PSEUDONYMISER)
    replay_window(extract, _window(10, 20), CONTEXT, second, PSEUDONYMISER)

    assert len(first.observations) == 1
    assert len(second.observations) == 1
