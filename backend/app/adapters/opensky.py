"""OpenSky replay adapter. Spec: adp-001.

Dialect translation and nothing else: Parquet rows in, source records out.
The adapter judges no row, converts nothing into a canonical observation, and
persists nothing -- `validate_record` and `ingest_batch` do all three. What
looks like a missing responsibility here is a deliberate one discharged at
the DAL, so a new adapter inherits it (`dal-003`, `dal-004`).

Three consequences that are easy to undo by accident:

* **Nothing is filtered.** A row with no position is emitted like any other
  and quarantined downstream. `adp-004` retained 500 of them precisely so
  `dal-002`'s quarantine path has real input; an adapter that dropped them
  would satisfy the null-position failure case by never exercising it.
* **Real `icao24` and `callsign` are emitted**, which is the precondition for
  `dal-004` rather than a breach of it: the DAL can only substitute an
  identifier that reaches it. An adapter supplying a ready-made `aircraft_id`
  would itself be the pseudonymiser.
* **No `app.corpus` import.** That module is the build-time tool that writes
  the artefact; this one is a replay-time consumer of it. The reader asks the
  file for its schema -- Parquet carries it -- rather than importing the
  writer's column list, so the two cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from app.dal.ingest import IngestResult, ingest_batch
from app.dal.models import ObservationType, SourceType
from app.dal.pseudonymise import Pseudonymiser
from app.dal.repository import ObservationRepository
from app.dal.validation import IngestContext

#: The source instance, not the source kind -- `SourceType.OPENSKY` is that.
SOURCE_ID = "opensky-replay"

#: Rows per batch pulled from the file. Bounds memory without making the
#: per-batch Python filter dominate the read.
BATCH_ROWS = 8192

#: The columns the adapter needs. Named so the reader does not pay for
#: `alert`, `spi` or `squawk`, none of which reach the canonical payload.
COLUMNS = (
    "time",
    "icao24",
    "lat",
    "lon",
    "velocity",
    "heading",
    "vertrate",
    "callsign",
    "onground",
    "baroaltitude",
    "geoaltitude",
    "lastposupdate",
    "lastcontact",
)

_MISSING_EXTRACT = (
    "OpenSky extract not found: {path}. The extract is not committed -- the "
    "licence forbids redistributing it -- so build it with "
    "`python -m app.corpus.build --accept-licence` (adp-006). The adapter "
    "will not fetch it: replays read from file only."
)


@dataclass(frozen=True)
class Window:
    """A half-open span of source time: `[start, end)`.

    Half-open so that adjacent windows tile the timeline exactly once. Closed
    intervals would put a boundary frame in both windows -- a duplicate that
    reads downstream as a zero-second inter-sample gap -- and open intervals
    would put it in neither, manufacturing a dropout indistinguishable from
    the one scenario type 4 injects.
    """

    start: datetime
    end: datetime


def available_window(manifest: Mapping[str, Any]) -> Window:
    """The span the extract covers, read from the manifest rather than the rows.

    Scanning the file to answer this would read the whole extract to learn
    what the manifest already records, and would make the corpus span a
    property of whichever rows survived filtering rather than of the recorded
    artefact.
    """
    start = datetime.fromisoformat(manifest["snapshot_hour"].replace("Z", "+00:00"))
    return Window(start=start, end=start + timedelta(hours=1))


def _staleness(frame_time: int, updated_at: float | None) -> float | None:
    """Age of a reported value at the moment its row was written.

    `None` rather than `0.0` when the source field is absent: zero asserts a
    perfectly fresh value for a row that has none, which would suppress the
    update-frequency rule this feeds. `TrackPayload` requires a float, so the
    `None` quarantines at the DAL -- which is the intended outcome, reached by
    the DAL's judgement rather than the adapter's.
    """
    if updated_at is None:
        return None
    return frame_time - updated_at


def _source_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """One extract row in the DAL's source-record shape.

    No provenance, no `data_mode`, no `scenario_run_id`: those describe the
    run rather than the record and arrive through `IngestContext`. A record
    supplying its own provenance is rejected outright (`dal-003`).
    """
    frame_time = row["time"]
    lat, lon = row["lat"], row["lon"]

    return {
        "source_id": SOURCE_ID,
        "source_type": SourceType.OPENSKY,
        "observation_type": ObservationType.TRACK,
        "timestamp": datetime.fromtimestamp(frame_time, tz=UTC),
        # Left as the source reported it, nulls included. A row with no
        # position cannot be placed, and inventing a default coordinate is
        # this item's first failure case.
        "location": {"lat": lat, "lon": lon},
        "payload": {
            "icao24": row["icao24"],
            "callsign": row["callsign"],
            # Barometric first: one consistent reference across the fleet,
            # and not the GNSS-derived field whose disruption is under study.
            # The fallback fires on zero rows of the current corpus -- the
            # null sets nest -- and is kept against a re-filtered box.
            "altitude_m": (
                row["baroaltitude"]
                if row["baroaltitude"] is not None
                else row["geoaltitude"]
            ),
            "velocity_ms": row["velocity"],
            "heading_deg": row["heading"],
            "vertical_rate_ms": row["vertrate"],
            "on_ground": row["onground"],
            "position_staleness_s": _staleness(frame_time, row["lastposupdate"]),
            "contact_staleness_s": _staleness(frame_time, row["lastcontact"]),
        },
    }


def read_window(path: Path, window: Window) -> Iterator[Mapping[str, Any]]:
    """Yield source records whose frame time falls in `[window.start, end)`.

    Streamed rather than materialised: the extract is 133,634 rows and a
    caller asking for the whole hour should not force it into memory. The
    window predicate is applied per batch in Python -- `iter_batches` takes no
    `filters`, and the artefact is a single row group, so there is nothing to
    push down.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(_MISSING_EXTRACT.format(path=path))

    start, end = window.start.timestamp(), window.end.timestamp()
    if end <= start:
        return

    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=BATCH_ROWS, columns=list(COLUMNS)):
        rows = batch.to_pylist()
        # Sorted per batch rather than assumed: the extract is written in
        # ascending time order, but continuity rules would read an
        # out-of-order emission as a negative gap, so it is not left to trust.
        rows.sort(key=lambda row: row["time"])
        for row in rows:
            if start <= row["time"] < end:
                yield _source_record(row)


def replay_window(
    path: Path,
    window: Window,
    context: IngestContext,
    repository: ObservationRepository,
    pseudonymiser: Pseudonymiser,
) -> IngestResult:
    """Drive one window through the DAL and report what it did.

    The repository and pseudonymiser are supplied rather than constructed:
    building either here would couple the adapter to a storage engine and to
    process configuration, and would break the seam `db-003` requires before
    it is built.
    """
    return ingest_batch(read_window(path, window), context, repository, pseudonymiser)
