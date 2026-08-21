"""Aircraft identifier pseudonymisation at the DAL. Spec: dal-004.

OpenSky DLA section 3(i) requires aircraft identifiers to be de-identified
for any publication or other disclosure. These tests prove the substitution
happens at the DAL rather than in an adapter, that it is stable enough for
track continuity to survive a replay, and that nothing about the source
identifier survives into the pseudonym.

The seed used here is a test seed. The real one is read from the
environment and is deliberately absent from the repository -- see the
amended spec item on why publishing it would reverse every pseudonym.
"""

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.corpus.extract import BoundingBox, build_manifest
from app.dal.ingest import ingest_batch
from app.dal.models import DataMode, ObservationType, SourceType
from app.dal.pseudonymise import Pseudonymiser
from app.dal.validation import IngestContext, validate_record
from tests.fakes import InMemoryObservationRepository

WHEN = datetime(2022, 6, 27, 12, 0, 0, tzinfo=timezone.utc)

CONTEXT = IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=7)

PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")

OTHER = Pseudonymiser(seed="a-different-test-seed")


def _track_record(**overrides: Any) -> dict[str, Any]:
    """A source record as the adapter emits it: real identifiers, still."""
    payload: dict[str, Any] = {
        "icao24": "3c6444",
        "callsign": "DLH8AT  ",
        "altitude_m": 5951.22,
        "velocity_ms": 194.26,
        "heading_deg": 135.64,
        "vertical_rate_ms": 13.32,
        "on_ground": False,
        "position_staleness_s": 1.06,
    }
    payload.update(overrides.pop("payload", {}))
    record: dict[str, Any] = {
        "source_id": "opensky-replay",
        "source_type": SourceType.OPENSKY,
        "observation_type": ObservationType.TRACK,
        "timestamp": WHEN,
        "location": {"lat": 51.09, "lon": 7.54},
        "payload": payload,
    }
    record.update(overrides)
    return record


def _observation_for(**payload: Any) -> Any:
    outcome = validate_record(_track_record(payload=payload), CONTEXT, PSEUDONYMISER)
    assert outcome.observation is not None, outcome.rejection
    return outcome.observation


# --- The substitution happens, and the source values do not survive ---------


def test_a_track_observation_carries_a_pseudonym_not_the_transponder_address() -> None:
    # spec: dal-004
    observation = _observation_for()

    assert observation.payload.aircraft_id != "3c6444"
    assert "3c6444" not in observation.payload.aircraft_id


def test_the_callsign_is_pseudonymised_too() -> None:
    # spec: dal-004
    observation = _observation_for()

    assert observation.payload.flight_id is not None
    assert "DLH8AT" not in observation.payload.flight_id


def test_no_source_identifier_survives_anywhere_in_the_observation() -> None:
    """The third failure case: retaining the source value beside the
    pseudonym satisfies the letter of the mapping and leaves the real value
    one query away."""
    # spec: dal-004
    observation = _observation_for()

    rendered = observation.model_dump_json()
    assert "3c6444" not in rendered
    assert "DLH8AT" not in rendered
    assert "icao24" not in rendered
    assert "callsign" not in rendered


def test_a_blank_callsign_yields_no_flight_id_rather_than_a_pseudonym() -> None:
    """OpenSky reports many of these. An empty callsign is missing data, and
    hashing the empty string would give every one of them one shared
    identity."""
    # spec: dal-004
    assert _observation_for(callsign="   ").payload.flight_id is None
    assert _observation_for(callsign="").payload.flight_id is None
    assert _observation_for(callsign=None).payload.flight_id is None


def test_a_track_record_without_an_icao24_is_quarantined() -> None:
    # spec: dal-004
    outcome = validate_record(
        _track_record(payload={"icao24": None}), CONTEXT, PSEUDONYMISER
    )

    assert not outcome.accepted
    assert outcome.rejection is not None
    assert "icao24" in outcome.rejection.field


# --- Stability: one aircraft, one pseudonym ---------------------------------


def test_the_same_aircraft_gets_the_same_pseudonym_every_time() -> None:
    """The second failure case: an aircraft carrying different pseudonyms in
    two runs against one corpus breaks track continuity and makes a batch
    non-comparable."""
    # spec: dal-004
    first = _observation_for()
    second = _observation_for()

    assert first.payload.aircraft_id == second.payload.aircraft_id
    assert first.payload.flight_id == second.payload.flight_id


def test_the_pseudonym_does_not_vary_with_the_scenario_run() -> None:
    """Deriving from the scenario seed produces exactly the second failure
    case, so the mapping must be blind to the run."""
    # spec: dal-004
    repository = InMemoryObservationRepository()
    run_one = IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=1)
    run_two = IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=2)

    ingest_batch([_track_record()], run_one, repository, PSEUDONYMISER)
    ingest_batch([_track_record()], run_two, repository, PSEUDONYMISER)

    first, second = repository.observations
    assert first.provenance.scenario_run_id != second.provenance.scenario_run_id
    assert first.payload.aircraft_id == second.payload.aircraft_id


def test_different_aircraft_get_different_pseudonyms() -> None:
    # spec: dal-004
    a = _observation_for(icao24="3c6444")
    b = _observation_for(icao24="3c6445")

    assert a.payload.aircraft_id != b.payload.aircraft_id


def test_the_corpus_icao24_space_does_not_collide() -> None:
    """The fifth failure case: a digest truncated far enough that two of the
    corpus's 1,445 airframes merge onto one pseudonym corrupts every
    continuity rule downstream and raises nothing."""
    # spec: dal-004
    addresses = [f"{value:06x}" for value in range(20_000)]

    pseudonyms = {PSEUDONYMISER.aircraft(address) for address in addresses}

    assert len(pseudonyms) == len(addresses)


def test_a_leading_zero_transponder_address_is_not_normalised_away() -> None:
    """`004321` and `4321` are different airframes; the corpus holds seven
    all-digit leading-zero addresses, which is what the Parquet schema in
    adp-004 exists to protect."""
    # spec: dal-004
    assert PSEUDONYMISER.aircraft("004321") != PSEUDONYMISER.aircraft("4321")


# --- The pseudonym carries no source information ----------------------------


def test_the_seed_changes_the_mapping() -> None:
    # spec: dal-004
    assert PSEUDONYMISER.aircraft("3c6444") != OTHER.aircraft("3c6444")


def test_a_country_block_does_not_survive_into_the_pseudonym() -> None:
    """`3c` is the German allocation. Aircraft sharing it must not share a
    recognisable prefix, or the pseudonym leaks the thing it removes."""
    # spec: dal-004
    german = [PSEUDONYMISER.aircraft(f"3c64{n:02x}") for n in range(16)]

    bodies = [pseudonym.split("-", 1)[1] for pseudonym in german]
    assert len({body[:3] for body in bodies}) > 1


def test_an_airline_prefix_does_not_survive_into_the_pseudonym() -> None:
    """Same argument for callsigns: `DLH` is Lufthansa."""
    # spec: dal-004
    lufthansa = [PSEUDONYMISER.flight(f"DLH{n:03d}") for n in range(16)]

    bodies = [pseudonym.split("-", 1)[1] for pseudonym in lufthansa if pseudonym]
    assert len({body[:3] for body in bodies}) > 1


def test_the_two_identifier_namespaces_are_separated() -> None:
    """An icao24 and a callsign that happen to share text must not collide."""
    # spec: dal-004
    assert PSEUDONYMISER.aircraft("ABC123") != PSEUDONYMISER.flight("ABC123")


# --- Enforced at the DAL, not in the adapter --------------------------------


def test_an_adapter_may_not_supply_the_pseudonym_itself() -> None:
    """The same enforcement dal-003 uses for provenance. If an adapter can
    hand over a finished aircraft_id, the DAL is no longer the sole source
    and a new adapter can pass a real address into an opaque-looking field."""
    # spec: dal-004
    outcome = validate_record(
        _track_record(payload={"aircraft_id": "AC-deadbeef"}), CONTEXT, PSEUDONYMISER
    )

    assert not outcome.accepted
    assert outcome.rejection is not None
    assert "aircraft_id" in outcome.rejection.field


def test_a_second_adapter_reaches_the_same_pseudonymiser() -> None:
    """dal-004 makes the same cross-cutting argument dal-003 makes: a source
    type with no identifiers passes through untouched rather than needing to
    know the rule exists."""
    # spec: dal-004
    repository = InMemoryObservationRepository()
    rf_record = {
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

    result = ingest_batch(
        [_track_record(), rf_record], CONTEXT, repository, PSEUDONYMISER
    )

    assert result.accepted == 2


# --- The seed is configuration, and is not in the repository ----------------


def test_a_pseudonymiser_cannot_be_built_without_a_seed() -> None:
    # spec: dal-004
    for empty in (None, "", "   "):
        with pytest.raises(ValidationError):
            Pseudonymiser(seed=empty)


def test_the_seed_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixed project configuration, held outside the repository."""
    # spec: dal-004
    monkeypatch.setenv("PSEUDONYM_SEED", "from-the-environment")

    assert Pseudonymiser.from_environment().seed == "from-the-environment"


def test_a_missing_seed_fails_loudly_rather_than_defaulting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A default seed would be a committed seed by another name."""
    # spec: dal-004
    monkeypatch.delenv("PSEUDONYM_SEED", raising=False)

    with pytest.raises(RuntimeError, match="PSEUDONYM_SEED"):
        Pseudonymiser.from_environment()


def test_the_seed_is_not_rendered_by_the_pseudonymiser() -> None:
    """Anything that repr's a Pseudonymiser -- a log line, a traceback, an
    error body -- must not print the seed, since printing it once publishes
    the reverse mapping."""
    # spec: dal-004
    assert "a-test-seed-not-the-real-one" not in repr(PSEUDONYMISER)
    assert "a-test-seed-not-the-real-one" not in str(PSEUDONYMISER)


def test_the_manifest_records_a_fingerprint_of_the_seed_not_the_seed() -> None:
    """The fourth failure case. The manifest is committed, so recording the
    seed there publishes it -- and a 24-bit icao24 space is exhaustively
    searchable in seconds."""
    # spec: dal-004
    fingerprint = PSEUDONYMISER.fingerprint()

    assert "a-test-seed-not-the-real-one" not in fingerprint
    assert len(fingerprint) == 64
    assert fingerprint == PSEUDONYMISER.fingerprint()
    assert fingerprint != OTHER.fingerprint()


def test_the_pseudonymiser_holds_no_reverse_mapping() -> None:
    """A cache keyed by source identifier would be a reverse mapping the
    application can read, which the item forbids."""
    # spec: dal-004
    before = dict(vars(PSEUDONYMISER))

    for value in range(500):
        PSEUDONYMISER.aircraft(f"{value:06x}")

    assert dict(vars(PSEUDONYMISER)) == before


def test_the_built_manifest_carries_the_fingerprint_and_not_the_seed() -> None:
    """The fourth failure case, at the artefact that actually gets committed.

    A seed in `data/opensky/manifest.json` is a published seed, and the
    24-bit icao24 space is exhaustively searchable in seconds.
    """
    # spec: dal-004
    manifest = build_manifest(
        source_url="https://example.invalid/x.csv.tar",
        snapshot_hour="2022-06-27T12:00:00Z",
        download_date="2026-08-21",
        original_sha256="6e0d2278",
        content_sha256="abc123",
        box=BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0),
        null_sample=500,
        null_retained=500,
        pseudonym_seed_sha256=PSEUDONYMISER.fingerprint(),
    )

    assert manifest["pseudonym_seed_sha256"] == PSEUDONYMISER.fingerprint()
    assert "a-test-seed-not-the-real-one" not in json.dumps(manifest)
    assert "seed" not in {key for key in manifest if key != "pseudonym_seed_sha256"}
