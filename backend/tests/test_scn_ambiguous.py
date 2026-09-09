"""The ambiguous type, and the zone both halves share. Spec: scn-002 (pass 3).

Pass 1 staged incidents on the RF grid, pass 2 on the replayed tracks. Neither
knew where the other was. That is fine for the two single-cause types and wrong
for everything else: a navigation incident centred on Rotterdam that froze the
positions of aircraft over Cologne is not an incident, it is two unrelated
things sharing a clock, and `anom-005` fuses on *co-location* in space as well
as in time.

So this pass adds the missing axis. One centre per run, derived from the seed
exactly as the RF zone already was, shared by both halves -- which makes
co-location structural rather than something a caller has to arrange, and gives
the coverage-gap type a zone of its own so its dropouts cluster instead of
scattering across the fleet.

**`ambiguous-mixed-evidence` is then a composition rather than new machinery**,
and that is the point of the design. One receiver deviating with clean
neighbours is what the sensor-fault rule reads as a broken receiver. A coverage
gap co-located with an RF anomaly is what the fusion rule reads as real
interference. Stage both, in one place, at one time, and both readings are
available and neither is safe -- which is the case the hypothesis layer is being
studied on, because it is where a confident answer is worse than an uncertain
one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.dal.pseudonymise import Pseudonymiser
from app.scenario.emitter import BaselineParameters, RunSpec, emit_baseline, emit_rf
from app.scenario.incident import (
    IncidentParameters,
    ScenarioType,
    ground_truth,
    plan_incident,
)
from app.scenario.layout import RfLayout, great_circle_km, load_layout
from app.scenario.tracks import TrackMode, TrackPerturber, plan_track_perturbation

PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")

SEED = 20220627
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
DURATION_SECONDS = 900
OFFSET_S = 120
WINDOW_S = 300
DURING = START + timedelta(seconds=OFFSET_S + 10)


@pytest.fixture()
def layout() -> RfLayout:
    return load_layout()


def _spec(
    *,
    scenario_type: ScenarioType = ScenarioType.AMBIGUOUS_MIXED_EVIDENCE,
    seed: int = SEED,
) -> RunSpec:
    return RunSpec(
        scenario_type=scenario_type,
        parameters=BaselineParameters(),
        incident=IncidentParameters(start_offset_s=OFFSET_S, duration_s=WINDOW_S),
        seed=seed,
        start=START,
        duration_seconds=DURATION_SECONDS,
    )


def _record(*, icao24: str, lat: float, lon: float, at: datetime = DURING) -> dict[str, Any]:
    return {
        "source_id": "opensky-replay",
        "source_type": "opensky",
        "observation_type": "track",
        "timestamp": at,
        "location": {"lat": lat, "lon": lon},
        "payload": {
            "icao24": icao24,
            "callsign": "CXI27NM ",
            "altitude_m": 5753.1,
            "velocity_ms": 194.26,
            "heading_deg": 135.64,
            "vertical_rate_ms": 13.33,
            "on_ground": False,
            "position_staleness_s": 1.06,
            "contact_staleness_s": 0.0,
        },
    }


def _perturber(layout: RfLayout, spec: RunSpec) -> TrackPerturber:
    perturbation = plan_track_perturbation(layout, spec)
    assert perturbation is not None
    return TrackPerturber(perturbation, pseudonymiser=PSEUDONYMISER)


def _a_targeted_identifier(perturber: TrackPerturber) -> str:
    return next(
        identifier
        for identifier in (f"{index:06x}" for index in range(500))
        if perturber.targets(identifier)
    )


# ------------------------------------------------------------- the shared zone


def test_both_halves_of_a_run_share_one_centre(layout: RfLayout) -> None:
    # spec: scn-002, anom-005
    # Co-location is what the fusion rule reads. Two independently placed
    # halves would make a scenario's own detectability depend on how far apart
    # they happened to land.
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    incident = plan_incident(layout, spec)
    perturbation = plan_track_perturbation(layout, spec)
    assert incident is not None and perturbation is not None

    centre = next(
        site
        for site in layout.sensors
        if site.sensor_id == incident.sensors[0] or site.sensor_id in incident.sensors
    )
    assert great_circle_km(
        perturbation.centre_lat, perturbation.centre_lon, centre.lat, centre.lon
    ) < perturbation.radius_km


def test_an_aircraft_outside_the_zone_is_never_touched(layout: RfLayout) -> None:
    # spec: scn-002
    # The axis pass 2 did not have. Without it a navigation incident over the
    # Randstad degrades an aircraft over the Rhineland, and the answer key says
    # they are the same event.
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    perturber = _perturber(layout, spec)
    target = _a_targeted_identifier(perturber)

    far = _record(icao24=target, lat=50.8659, lon=7.1427)
    assert perturber.apply(far) == far


def test_an_aircraft_inside_the_zone_is_perturbed(layout: RfLayout) -> None:
    # spec: scn-002
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    perturbation = plan_track_perturbation(layout, spec)
    assert perturbation is not None
    perturber = TrackPerturber(perturbation, pseudonymiser=PSEUDONYMISER)
    target = _a_targeted_identifier(perturber)

    near = _record(
        icao24=target,
        lat=perturbation.centre_lat,
        lon=perturbation.centre_lon,
    )
    perturbed = perturber.apply(near)

    assert perturbed is not None
    assert perturbed["payload"]["position_staleness_s"] > 10.0


def test_a_coverage_gap_has_a_zone_but_no_radio_incident(layout: RfLayout) -> None:
    # spec: scn-002, anom-006
    # Dropouts have to cluster or anom-004 has nothing to group, and there must
    # be no co-located RF anomaly or anom-006 stops being the rule that
    # distinguishes a data-source problem from interference.
    spec = _spec(scenario_type=ScenarioType.AIRCRAFT_COVERAGE_GAP)

    assert plan_incident(layout, spec) is None
    perturbation = plan_track_perturbation(layout, spec)
    assert perturbation is not None
    assert perturbation.radius_km > 0


def test_a_record_with_no_position_is_left_alone(layout: RfLayout) -> None:
    # spec: scn-002, dal-001
    # A row with no coordinate cannot be tested against a zone. It is going to
    # quarantine on the missing position anyway, and inventing a location to
    # decide whether to perturb it would be inventing data.
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    perturber = _perturber(layout, spec)
    target = _a_targeted_identifier(perturber)

    record = _record(icao24=target, lat=52.0, lon=4.5)
    record["location"] = {"lat": None, "lon": None}

    assert perturber.apply(record) == record


# ---------------------------------------------------- the ambiguous scenario


def test_the_ambiguous_run_stages_one_deviating_receiver(layout: RfLayout) -> None:
    # spec: scn-002, anom-007
    incident = plan_incident(layout, _spec())
    assert incident is not None

    assert len(incident.sensors) == 1


def test_the_ambiguous_runs_neighbours_stay_clean(layout: RfLayout) -> None:
    # spec: scn-002, anom-007
    # Half of what makes it ambiguous: this is exactly the pattern the
    # sensor-fault rule reads as a broken receiver.
    spec = _spec()
    incident = plan_incident(layout, spec)
    assert incident is not None

    injected = {
        (r["timestamp"], r["payload"]["sensor_id"], r["payload"]["channel_index"]): r[
            "payload"
        ]
        for r in emit_rf(layout, spec, incident)
    }
    quiet = {
        (r["timestamp"], r["payload"]["sensor_id"], r["payload"]["channel_index"]): r[
            "payload"
        ]
        for r in emit_baseline(layout, spec)
    }

    for neighbour in layout.neighbours(incident.sensors[0]):
        for cell, payload in injected.items():
            if cell[1] == neighbour:
                assert payload == quiet[cell]


def test_the_ambiguous_run_also_stages_a_co_located_gap(layout: RfLayout) -> None:
    # spec: scn-002, anom-005
    # The other half: a coverage gap in the same place and window is what the
    # fusion rule reads as real interference. Both readings are now available
    # and neither is safe, which is the whole point of the type.
    spec = _spec()
    incident = plan_incident(layout, spec)
    perturbation = plan_track_perturbation(layout, spec)
    assert incident is not None and perturbation is not None

    assert perturbation.mode is TrackMode.SUPPRESS
    assert perturbation.start == incident.start
    assert perturbation.end == incident.end

    deviating = next(
        site for site in layout.sensors if site.sensor_id == incident.sensors[0]
    )
    assert (
        great_circle_km(
            perturbation.centre_lat, perturbation.centre_lon, deviating.lat, deviating.lon
        )
        < 1.0
    )


def test_the_ambiguous_run_suppresses_rather_than_freezes(layout: RfLayout) -> None:
    # spec: scn-002
    # A frozen position would name the cause: it is the navigation signature,
    # and the run would stop being ambiguous about which explanation fits.
    spec = _spec()
    perturbation = plan_track_perturbation(layout, spec)
    assert perturbation is not None
    perturber = TrackPerturber(perturbation, pseudonymiser=PSEUDONYMISER)
    target = _a_targeted_identifier(perturber)

    inside = _record(
        icao24=target, lat=perturbation.centre_lat, lon=perturbation.centre_lon
    )

    assert perturber.apply(inside) is None


# ------------------------------------------------------------- ground truth


def test_the_ambiguous_ground_truth_records_both_halves(layout: RfLayout) -> None:
    # spec: scn-002
    spec = _spec()
    incident = plan_incident(layout, spec)
    perturbation = plan_track_perturbation(layout, spec)
    assert incident is not None and perturbation is not None
    perturber = TrackPerturber(perturbation, pseudonymiser=PSEUDONYMISER)
    target = _a_targeted_identifier(perturber)
    perturber.apply(
        _record(icao24=target, lat=perturbation.centre_lat, lon=perturbation.centre_lon)
    )

    truth = ground_truth(spec, incident, perturber)

    assert truth["scenario_type"] == "ambiguous-mixed-evidence"
    assert len(truth["sensors"]) == 1
    assert truth["track_mode"] == TrackMode.SUPPRESS.value
    assert truth["aircraft"]
    assert truth["window"] is not None


def test_the_zone_moves_with_the_seed(layout: RfLayout) -> None:
    # spec: scn-002, scn-001
    centres = {
        (
            plan_track_perturbation(layout, _spec(seed=seed)).centre_lat,  # type: ignore[union-attr]
            plan_track_perturbation(layout, _spec(seed=seed)).centre_lon,  # type: ignore[union-attr]
        )
        for seed in range(SEED, SEED + 12)
    }

    assert len(centres) > 1
