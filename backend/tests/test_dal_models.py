"""Canonical observation model and required-field validation. Spec: dal-001.

Every test here proves part of dal-001: that one model serves every source,
that its payload is typed per observation type, and that a record missing a
required field yields no canonical observation at all.

Nothing here touches a database. dal-001 is pure model and validation --
where an accepted observation is *written* is dal-002's repository port, and
whether the schema also refuses a bad one is db-001's NOT NULL constraints.
"""

from datetime import datetime, timezone
from typing import Any

import pytest

from app.dal.models import (
    CanonicalObservation,
    DataMode,
    Location,
    ObservationType,
    Provenance,
    RfPayload,
    SourceType,
    TrackPayload,
    ValidationStatus,
)
from app.dal.pseudonymise import Pseudonymiser
from app.dal.validation import IngestContext, validate_record

WHEN = datetime(2022, 6, 27, 12, 0, 0, tzinfo=timezone.utc)

CONTEXT = IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=7)

PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")


def _track_record(**overrides: Any) -> dict[str, Any]:
    """A source record as the OpenSky replay adapter would emit one.

    `aircraft_id` is already opaque. The canonical model never carries
    `icao24` or `callsign` under any name, so dal-004 changes how this value
    is *derived*, not the shape of the record -- which is the whole point of
    building pseudonymisation before adp-001 replays a real row.
    """
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
        },
    }
    record.update(overrides)
    return record


def _rf_record(**overrides: Any) -> dict[str, Any]:
    """A source record as the synthetic RF adapter would emit one."""
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


# --- One model for every source (FR-101) -----------------------------------


def test_valid_track_record_produces_a_canonical_observation() -> None:
    # spec: dal-001
    outcome = validate_record(_track_record(), CONTEXT, PSEUDONYMISER)

    assert outcome.accepted
    observation = outcome.observation
    assert observation is not None
    assert observation.source_id == "opensky-replay"
    assert observation.source_type is SourceType.OPENSKY
    assert observation.observation_type is ObservationType.TRACK
    assert observation.timestamp == WHEN
    assert observation.location == Location(lat=51.09, lon=7.54)
    assert observation.data_mode is DataMode.REPLAYED
    assert observation.validation_status is ValidationStatus.VALID
    assert isinstance(observation.provenance, Provenance)
    assert isinstance(observation.payload, TrackPayload)


def test_valid_rf_record_produces_a_canonical_observation() -> None:
    # spec: dal-001
    outcome = validate_record(_rf_record(), CONTEXT, PSEUDONYMISER)

    assert outcome.accepted
    observation = outcome.observation
    assert observation is not None
    assert observation.observation_type is ObservationType.RF
    assert observation.location == Location(lat=52.31, lon=4.76)
    assert isinstance(observation.payload, RfPayload)


def test_both_sources_normalise_into_the_same_model() -> None:
    """FR-101: one canonical model regardless of source."""
    # spec: dal-001
    track = validate_record(_track_record(), CONTEXT, PSEUDONYMISER).observation
    rf = validate_record(_rf_record(), CONTEXT, PSEUDONYMISER).observation

    assert type(track) is CanonicalObservation
    assert type(rf) is CanonicalObservation
    assert type(track.payload) is not type(rf.payload)


def test_payload_is_a_typed_model_not_a_raw_mapping() -> None:
    """Specialisations live in the payload, typed via Pydantic (section 9)."""
    # spec: dal-001
    track = validate_record(_track_record(), CONTEXT, PSEUDONYMISER).observation
    assert track is not None
    assert not isinstance(track.payload, dict)
    assert track.payload.aircraft_id == PSEUDONYMISER.aircraft("3c6444")
    assert track.payload.position_staleness_s == pytest.approx(1.06)


# --- Required-field validation (FR-102) ------------------------------------


def test_a_record_missing_its_timestamp_is_rejected() -> None:
    # spec: dal-001
    record = _track_record()
    del record["timestamp"]

    outcome = validate_record(record, CONTEXT, PSEUDONYMISER)

    assert not outcome.accepted
    assert outcome.rejection is not None
    assert outcome.rejection.field == "timestamp"
    assert outcome.rejection.reason


def test_a_record_missing_its_location_is_rejected() -> None:
    # spec: dal-001
    record = _rf_record()
    del record["location"]

    outcome = validate_record(record, CONTEXT, PSEUDONYMISER)

    assert not outcome.accepted
    assert outcome.rejection is not None
    assert outcome.rejection.field == "location"


def test_a_rejected_record_produces_no_canonical_observation() -> None:
    """The spec's failure case: not a degraded observation, none at all."""
    # spec: dal-001
    record = _track_record()
    del record["timestamp"]

    outcome = validate_record(record, CONTEXT, PSEUDONYMISER)

    assert outcome.observation is None


def test_a_null_coordinate_is_rejected_rather_than_defaulted() -> None:
    """The real corpus carries these; adp-004 retains 500 of them on purpose."""
    # spec: dal-001
    outcome = validate_record(
        _track_record(location={"lat": None, "lon": 7.54}), CONTEXT, PSEUDONYMISER
    )

    assert not outcome.accepted
    assert outcome.observation is None
    assert outcome.rejection is not None
    assert outcome.rejection.field == "location"


def test_an_out_of_range_latitude_is_rejected() -> None:
    # spec: dal-001
    outcome = validate_record(
        _track_record(location={"lat": 91.5, "lon": 7.54}), CONTEXT, PSEUDONYMISER
    )

    assert not outcome.accepted
    assert outcome.rejection is not None
    assert outcome.rejection.field == "location"


def test_a_payload_missing_a_required_field_is_rejected() -> None:
    # spec: dal-001
    payload = _rf_record()["payload"]
    del payload["channel_index"]

    outcome = validate_record(_rf_record(payload=payload), CONTEXT, PSEUDONYMISER)

    assert not outcome.accepted
    assert outcome.rejection is not None
    assert "channel_index" in outcome.rejection.field


def test_a_payload_must_match_its_observation_type() -> None:
    """A track observation carrying an RF payload is not a track observation."""
    # spec: dal-001
    outcome = validate_record(
        _track_record(payload=_rf_record()["payload"]), CONTEXT, PSEUDONYMISER
    )

    assert not outcome.accepted
    assert outcome.observation is None


def test_an_unknown_observation_type_is_rejected() -> None:
    # spec: dal-001
    outcome = validate_record(
        _track_record(observation_type="telepathy"), CONTEXT, PSEUDONYMISER
    )

    assert not outcome.accepted
    assert outcome.rejection is not None
    assert outcome.rejection.field == "observation_type"


# --- Structural guards ------------------------------------------------------


def test_location_carries_coordinates_not_a_storage_engine_type() -> None:
    """dal-002's second failure case, guarded at the model.

    A WKT or WKB string here would mean the DAL knows about PostGIS, and the
    repository seam db-003 requires would already be broken.
    """
    # spec: dal-001
    observation = validate_record(_track_record(), CONTEXT, PSEUDONYMISER).observation
    assert observation is not None

    assert isinstance(observation.location.lat, float)
    assert isinstance(observation.location.lon, float)
    assert not hasattr(observation.location, "wkt")
    assert not hasattr(observation.location, "wkb")
    assert not hasattr(observation.location, "srid")


def test_the_canonical_model_has_no_field_for_a_source_aircraft_identifier() -> None:
    """dal-004's third failure case, made unrepresentable rather than checked.

    OpenSky DLA section 3(i) requires aircraft identifiers to be
    de-identified for any disclosure. If no field can hold `icao24` or
    `callsign`, retaining one alongside a pseudonym is not an oversight that
    a later review has to catch.
    """
    # spec: dal-001
    forbidden = {"icao24", "callsign"}

    # Assert the payload is populated and its aircraft reference is opaque
    # first: `isdisjoint` is trivially true of a model with no fields, so
    # without this the test would pass against an empty stub.
    assert "aircraft_id" in TrackPayload.model_fields

    for model in (CanonicalObservation, TrackPayload, RfPayload, Provenance):
        assert model.model_fields, model.__name__
        assert forbidden.isdisjoint(model.model_fields), model.__name__


def test_an_accepted_observation_is_immutable() -> None:
    """Validation runs before persistence, so a validated record must stay
    validated -- a mutable one could be edited past its own check."""
    # spec: dal-001
    observation = validate_record(_track_record(), CONTEXT, PSEUDONYMISER).observation
    assert observation is not None

    with pytest.raises(Exception):
        observation.source_id = "somewhere-else"


def test_an_unknown_source_type_is_rejected() -> None:
    # spec: dal-001
    outcome = validate_record(
        _track_record(source_type="carrier-pigeon"), CONTEXT, PSEUDONYMISER
    )

    assert not outcome.accepted
    assert outcome.rejection is not None
    assert outcome.rejection.field == "source_type"


def test_a_malformed_timestamp_is_rejected() -> None:
    """Present but unparseable is a different failure from absent, and the
    corpus can produce either."""
    # spec: dal-001
    outcome = validate_record(
        _track_record(timestamp="half past four"), CONTEXT, PSEUDONYMISER
    )

    assert not outcome.accepted
    assert outcome.observation is None
    assert outcome.rejection is not None
    assert outcome.rejection.field == "timestamp"


def test_the_model_itself_refuses_a_mismatched_payload() -> None:
    """The type/payload agreement is a property of the model, not of the
    validator, so it holds for anything constructed directly."""
    # spec: dal-001
    provenance = Provenance(
        source_id="opensky-replay",
        source_type=SourceType.OPENSKY,
        data_mode=DataMode.REPLAYED,
        scenario_run_id=7,
    )

    with pytest.raises(ValueError, match="track observation requires TrackPayload"):
        CanonicalObservation(
            source_id="opensky-replay",
            source_type=SourceType.OPENSKY,
            observation_type=ObservationType.TRACK,
            timestamp=WHEN,
            location=Location(lat=51.09, lon=7.54),
            data_mode=DataMode.REPLAYED,
            validation_status=ValidationStatus.VALID,
            provenance=provenance,
            payload=RfPayload.model_validate(_rf_record()["payload"]),
        )
