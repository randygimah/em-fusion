"""Quarantine and provenance at the DAL. Spec: dal-002, dal-003.

These two are one code path and are tested together: an ingest run splits a
batch into accepted observations and quarantine records, and stamps
provenance on everything it accepts. Testing them apart would mean building
the same harness twice.

Persistence is reached through the repository port and satisfied here by an
in-memory fake. What that proves is that the DAL behaves correctly, not that
the schema would also have refused a bad record -- the NOT NULL constraints
over the same fields are db-001's, and are asserted there.
"""

from datetime import datetime, timezone
from typing import Any, get_type_hints

import pytest
from pydantic import ValidationError

from app.dal.ingest import ingest_batch
from app.dal.models import (
    DataMode,
    ObservationType,
    Provenance,
    SourceType,
)
from app.dal.pseudonymise import Pseudonymiser
from app.dal.repository import ObservationRepository, QuarantineRecord
from app.dal.validation import IngestContext
from tests.fakes import FailingObservationRepository, InMemoryObservationRepository

WHEN = datetime(2022, 6, 27, 12, 0, 0, tzinfo=timezone.utc)

CONTEXT = IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=7)

PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")


def _track_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_id": "opensky-replay",
        "source_type": SourceType.OPENSKY,
        "observation_type": ObservationType.TRACK,
        "timestamp": WHEN,
        "location": {"lat": 51.09, "lon": 7.54},
        "payload": {
            "icao24": "3c6444",
            "callsign": "DLH8AT  ",
            "altitude_m": 5951.22,
            "velocity_ms": 194.26,
            "heading_deg": 135.64,
            "vertical_rate_ms": 13.32,
            "on_ground": False,
            "position_staleness_s": 1.06,
            "contact_staleness_s": 0.02,
        },
    }
    record.update(overrides)
    return record


def _rf_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_id": "rf-sensor-03",
        "source_type": SourceType.SYNTHETIC_RF,
        "observation_type": ObservationType.RF,
        "timestamp": WHEN,
        "location": {"lat": 52.31, "lon": 4.76},
        "payload": {
            "sensor_id": "rf-sensor-03",
            "channel_index": 4,
            "centre_frequency_mhz": 1575.42,
            "band": "L1",
            "power_dbm": -112.4,
            "snr_db": 8.9,
            "bandwidth_mhz": 2.0,
            "signal_type": "gnss",
            "baseline_delta_db": 0.3,
        },
    }
    record.update(overrides)
    return record


def _broken_record() -> dict[str, Any]:
    """A row of the shape the real corpus supplies 500 of: no position."""
    return _track_record(location={"lat": None, "lon": 7.54})


def _mixed_batch() -> list[dict[str, Any]]:
    """Ten records, three of them invalid, invalid ones not last.

    The ordering matters: an implementation that stops at the first failure
    would still pass a batch whose bad records trail the good ones.
    """
    batch: list[dict[str, Any]] = []
    for index in range(10):
        if index in (0, 4, 7):
            batch.append(_broken_record())
        else:
            batch.append(_track_record())
    return batch


# --- dal-002: quarantine ----------------------------------------------------


def test_a_mixed_batch_persists_the_valid_and_quarantines_the_invalid() -> None:
    """The spec's headline failure case, stated as the positive behaviour."""
    # spec: dal-002
    repository = InMemoryObservationRepository()

    result = ingest_batch(_mixed_batch(), CONTEXT, repository, PSEUDONYMISER)

    assert len(repository.observations) == 7
    assert len(repository.quarantined) == 3
    assert result.accepted == 7
    assert result.quarantined == 3


def test_an_invalid_record_does_not_abort_the_ingest_run() -> None:
    """The first record in the batch is broken; the rest must still land."""
    # spec: dal-002
    repository = InMemoryObservationRepository()

    ingest_batch(_mixed_batch(), CONTEXT, repository, PSEUDONYMISER)  # must not raise

    assert repository.observations


def test_nothing_is_silently_dropped() -> None:
    # spec: dal-002
    batch = _mixed_batch()
    repository = InMemoryObservationRepository()

    result = ingest_batch(batch, CONTEXT, repository, PSEUDONYMISER)

    assert result.accepted + result.quarantined == len(batch)


def test_a_quarantine_record_carries_the_failing_field_and_the_reason() -> None:
    """A quarantine row that cannot say what was wrong is a silent drop with
    extra steps."""
    # spec: dal-002
    repository = InMemoryObservationRepository()

    ingest_batch([_broken_record()], CONTEXT, repository, PSEUDONYMISER)

    (quarantined,) = repository.quarantined
    assert quarantined.field == "location"
    assert quarantined.reason


def test_a_quarantine_record_carries_its_source_attribution() -> None:
    # spec: dal-002
    repository = InMemoryObservationRepository()

    ingest_batch([_broken_record()], CONTEXT, repository, PSEUDONYMISER)

    (quarantined,) = repository.quarantined
    assert quarantined.source_id == "opensky-replay"
    assert quarantined.source_type == SourceType.OPENSKY.value
    assert quarantined.scenario_run_id == 7


def test_a_record_missing_its_source_id_is_still_attributable_to_the_run() -> None:
    """Attribution is best-effort, because the record may be missing the very
    field that identifies it -- but the run is always known."""
    # spec: dal-002
    record = _track_record()
    del record["source_id"]
    repository = InMemoryObservationRepository()

    ingest_batch([record], CONTEXT, repository, PSEUDONYMISER)

    (quarantined,) = repository.quarantined
    assert quarantined.source_id is None
    assert quarantined.field == "source_id"
    assert quarantined.scenario_run_id == 7


def test_a_quarantine_record_has_nowhere_to_hold_the_raw_source_row() -> None:
    """A quarantined OpenSky row still carries a real icao24. Storing it for
    debugging would put source identifiers in the database that dal-004
    exists to keep out, so the failing field and reason are kept and the row
    is not."""
    # spec: dal-002
    forbidden = {"raw", "raw_record", "record", "source_record", "payload"}
    assert forbidden.isdisjoint(QuarantineRecord.model_fields)
    assert {"field", "reason", "scenario_run_id"} <= set(QuarantineRecord.model_fields)


def test_observations_and_quarantine_records_are_written_together() -> None:
    """dal-002's unit of work: one call, so there is no window in which
    observations are persisted and their quarantine rows are not."""
    # spec: dal-002
    repository = InMemoryObservationRepository()

    ingest_batch(_mixed_batch(), CONTEXT, repository, PSEUDONYMISER)

    assert repository.calls == 1


def test_a_failing_repository_leaves_nothing_persisted() -> None:
    # spec: dal-002
    repository = FailingObservationRepository()

    # Matched on the message, and the call asserted: NotImplementedError is a
    # RuntimeError, so a bare `raises(RuntimeError)` would pass against an
    # unbuilt ingest and prove nothing about the write.
    with pytest.raises(RuntimeError, match="not having it"):
        ingest_batch(_mixed_batch(), CONTEXT, repository, PSEUDONYMISER)

    assert repository.calls == 1
    assert repository.observations == []
    assert repository.quarantined == []


def test_an_empty_batch_writes_nothing_and_does_not_raise() -> None:
    # spec: dal-002
    repository = InMemoryObservationRepository()

    result = ingest_batch([], CONTEXT, repository, PSEUDONYMISER)

    assert result.accepted == 0
    assert result.quarantined == 0
    assert repository.calls == 0


def test_the_repository_port_carries_no_storage_engine_type() -> None:
    """dal-002's second failure case. A session, an engine, or a WKB string
    in this signature would mean the DAL knows about PostGIS, and the seam
    db-003 requires would be broken before it was built."""
    # spec: dal-002
    rendered = " ".join(
        str(hint) for hint in get_type_hints(ObservationRepository.save_batch).values()
    )

    assert "CanonicalObservation" in rendered
    assert "QuarantineRecord" in rendered
    for leak in ("Session", "Engine", "Connection", "sqlalchemy", "wkt", "wkb", "srid"):
        assert leak.lower() not in rendered.lower(), leak


# --- dal-003: provenance ----------------------------------------------------


def test_every_accepted_observation_carries_provenance() -> None:
    # spec: dal-003
    repository = InMemoryObservationRepository()

    ingest_batch(_mixed_batch(), CONTEXT, repository, PSEUDONYMISER)

    assert repository.observations
    for observation in repository.observations:
        assert observation.provenance.source_id == "opensky-replay"
        assert observation.provenance.source_type is SourceType.OPENSKY
        assert observation.provenance.data_mode is DataMode.REPLAYED
        assert observation.provenance.scenario_run_id == 7


def test_two_different_adapters_get_provenance_from_the_same_entrypoint() -> None:
    """dal-003's second failure case: provenance applied inside an adapter
    passes that adapter's own tests while leaving the next one free to omit
    it. Driving two source shapes through one entrypoint is what proves the
    attachment is the DAL's and not the adapter's."""
    # spec: dal-003
    repository = InMemoryObservationRepository()

    ingest_batch([_track_record(), _rf_record()], CONTEXT, repository, PSEUDONYMISER)

    track, rf = repository.observations
    assert track.provenance.source_type is SourceType.OPENSKY
    assert rf.provenance.source_type is SourceType.SYNTHETIC_RF
    assert track.provenance.scenario_run_id == rf.provenance.scenario_run_id == 7
    assert track.provenance.data_mode is rf.provenance.data_mode is DataMode.REPLAYED


def test_an_adapter_may_not_supply_its_own_provenance() -> None:
    """Attachment at the DAL is only guaranteed if the DAL is the sole
    source. A record arriving with provenance already on it is an adapter
    doing the DAL's job, so it is refused rather than quietly overwritten."""
    # spec: dal-003
    record = _track_record(
        provenance={
            "source_id": "somewhere-else",
            "source_type": "opensky",
            "data_mode": "synthetic",
            "scenario_run_id": 999,
        }
    )
    repository = InMemoryObservationRepository()

    result = ingest_batch([record], CONTEXT, repository, PSEUDONYMISER)

    assert result.accepted == 0
    assert repository.observations == []
    (quarantined,) = repository.quarantined
    assert quarantined.field == "provenance"


def test_data_mode_distinguishes_replayed_from_synthetic() -> None:
    """The SYNTHETIC ENVIRONMENT DATA badge reflects the data, not a UI
    constant, so the distinction has to survive the DAL."""
    # spec: dal-003
    synthetic = IngestContext(data_mode=DataMode.SYNTHETIC, scenario_run_id=11)
    repository = InMemoryObservationRepository()

    ingest_batch([_rf_record()], CONTEXT, repository, PSEUDONYMISER)
    ingest_batch([_rf_record()], synthetic, repository, PSEUDONYMISER)

    replayed_observation, synthetic_observation = repository.observations
    assert replayed_observation.data_mode is DataMode.REPLAYED
    assert synthetic_observation.data_mode is DataMode.SYNTHETIC
    assert synthetic_observation.provenance.data_mode is DataMode.SYNTHETIC


def test_an_ingest_context_without_a_scenario_run_id_is_rejected() -> None:
    # spec: dal-003
    with pytest.raises(ValidationError):
        IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=None)


def test_an_ingest_context_without_a_data_mode_is_rejected() -> None:
    # spec: dal-003
    with pytest.raises(ValidationError):
        IngestContext(data_mode=None, scenario_run_id=7)


def test_provenance_itself_refuses_an_absent_run_or_data_mode() -> None:
    """The DAL half of dal-003's first failure case. The other half is
    db-001's NOT NULL constraints, asserted there rather than here."""
    # spec: dal-003
    complete = {
        "source_id": "opensky-replay",
        "source_type": SourceType.OPENSKY,
        "data_mode": DataMode.REPLAYED,
        "scenario_run_id": 7,
    }

    assert Provenance(**complete)

    for missing in ("scenario_run_id", "data_mode"):
        with pytest.raises(ValidationError):
            Provenance(**{**complete, missing: None})
