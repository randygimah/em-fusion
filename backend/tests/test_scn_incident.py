"""Scenario types, the RF half. Spec: scn-002 (pass 1 of 3).

`scn-001` built the quiet background: a noise floor with seeded per-cell
variation and nothing wrong in it. This is the first half of what makes a run
an *incident* -- what gets added to that floor, where, in which slices of the
band, and during which window -- together with the answer key that says so.

Three of the five types are exercised here. `aircraft-coverage-gap` perturbs
replayed tracks rather than the RF grid and lands in pass 2;
`ambiguous-mixed-evidence` composes both and lands in pass 3.

Two properties matter more than the signatures themselves, and both would be
easy to lose:

* **The injection adds; it does not move.** A cell the incident does not touch
  must hold exactly the reading the same seed's `normal-baseline` run produced.
  This is what `scn-001`'s keyed derivation was chosen to make possible, and it
  is the difference between an answer key that describes the stream and one
  that described it before an unrelated change shifted every value.
* **No observation may carry the answer.** Not the scenario type, not the
  ground truth, and not by implication either: an injected cell labelled
  `interference` while a quiet one says `noise` is the answer key written onto
  every record, in a field an analyst and a detector can both read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.scenario.emitter import BaselineParameters, RunSpec, emit_baseline, emit_rf
from app.scenario.incident import (
    IncidentParameters,
    ScenarioType,
    SpectralExtent,
    ground_truth,
    plan_incident,
)
from app.scenario.layout import L1_CENTRE_MHZ, RfLayout, load_layout

SEED = 20220627
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
DURATION_SECONDS = 600

#: The incident occupies the middle of the run: 120 s in, for 300 s. Chosen so
#: there are quiet ticks on both sides of it, because a window covering the
#: whole run makes "outside the window" untestable.
OFFSET_S = 120
WINDOW_S = 300


@pytest.fixture()
def layout() -> RfLayout:
    return load_layout()


def _spec(
    *,
    scenario_type: ScenarioType = ScenarioType.GNSS_DEGRADATION,
    seed: int = SEED,
    incident: IncidentParameters | None = None,
) -> RunSpec:
    return RunSpec(
        scenario_type=scenario_type,
        parameters=BaselineParameters(),
        incident=incident if incident is not None else IncidentParameters(),
        seed=seed,
        start=START,
        duration_seconds=DURATION_SECONDS,
    )


def _cell(record: dict[str, Any]) -> tuple[Any, str, int]:
    return (
        record["timestamp"],
        record["payload"]["sensor_id"],
        record["payload"]["channel_index"],
    )


def _by_cell(records: tuple[dict[str, Any], ...]) -> dict[tuple[Any, str, int], Any]:
    return {_cell(record): record["payload"] for record in records}


def _run(layout: RfLayout, spec: RunSpec) -> tuple[Any, ...]:
    """Plan the incident and emit the stream it produces."""
    incident = plan_incident(layout, spec)
    return emit_rf(layout, spec, incident)


def _baseline(layout: RfLayout, spec: RunSpec) -> tuple[Any, ...]:
    """The same seed's quiet run, for comparison."""
    return emit_baseline(layout, spec)


# ------------------------------------------------------------ the five types


def test_there_are_exactly_five_scenario_types() -> None:
    # spec: scn-002
    # Broadband interference is a parameter of gnss-degradation, not a sixth
    # type. A sixth member here is the spec's second failure case.
    assert {member.value for member in ScenarioType} == {
        "normal-baseline",
        "gnss-degradation",
        "rf-sensor-fault",
        "aircraft-coverage-gap",
        "ambiguous-mixed-evidence",
    }


def test_normal_baseline_plans_no_incident(layout: RfLayout) -> None:
    # spec: scn-002
    assert (
        plan_incident(layout, _spec(scenario_type=ScenarioType.NORMAL_BASELINE)) is None
    )


def test_normal_baseline_is_byte_identical_to_the_quiet_run(layout: RfLayout) -> None:
    # spec: scn-002, anom-008
    # The first failure case, and the reason the false-positive rate means
    # anything: the control must inject nothing at all, not a little.
    spec = _spec(scenario_type=ScenarioType.NORMAL_BASELINE)

    assert _run(layout, spec) == _baseline(layout, spec)


# ------------------------------------------------------- gnss-degradation


def test_gnss_degradation_raises_the_l1_channel_only_when_narrowband(
    layout: RfLayout,
) -> None:
    # spec: scn-002
    spec = _spec(incident=IncidentParameters(spectral_extent=SpectralExtent.NARROWBAND))
    incident = plan_incident(layout, spec)
    assert incident is not None

    l1 = next(
        channel.index
        for channel in layout.channels
        if channel.centre_frequency_mhz == L1_CENTRE_MHZ
    )
    assert incident.channels == (l1,)


def test_gnss_degradation_raises_every_channel_when_broadband(
    layout: RfLayout,
) -> None:
    # spec: scn-002
    # Spectral extent is a parameter of this type. The distinction is what
    # anom-007 weighs when deciding sensor fault against environment, so it has
    # to be producible from the same type rather than from a sixth one.
    spec = _spec(incident=IncidentParameters(spectral_extent=SpectralExtent.BROADBAND))
    incident = plan_incident(layout, spec)
    assert incident is not None

    assert incident.channels == tuple(channel.index for channel in layout.channels)


def test_the_affected_sensors_are_the_neighbours_of_the_chosen_centre(
    layout: RfLayout,
) -> None:
    # spec: scn-002, scn-005
    # An interference zone contains some sensors and excludes others -- which
    # is the property scn-005 validates the layout for. A run that affected
    # every sensor would leave anom-005 nothing to discriminate.
    incident = plan_incident(layout, _spec())
    assert incident is not None

    assert 0 < len(incident.sensors) < len(layout.sensors)


def test_the_power_rises_inside_the_window_on_the_affected_cells(
    layout: RfLayout,
) -> None:
    # spec: scn-002
    spec = _spec()
    incident = plan_incident(layout, spec)
    assert incident is not None

    injected = _by_cell(emit_rf(layout, spec, incident))
    quiet = _by_cell(_baseline(layout, spec))

    raised = [
        cell
        for cell, payload in injected.items()
        if payload["power_dbm"] > quiet[cell]["power_dbm"]
    ]

    assert raised
    for timestamp, sensor_id, channel_index in raised:
        assert sensor_id in incident.sensors
        assert channel_index in incident.channels
        assert incident.start <= timestamp < incident.end


def test_every_untouched_cell_is_identical_to_the_quiet_run(
    layout: RfLayout,
) -> None:
    # spec: scn-002, scn-001
    # The third failure case. Adding the injection must not move the noise: a
    # ground truth recorded against a stream whose untouched cells shifted is a
    # ground truth describing something else.
    spec = _spec()
    incident = plan_incident(layout, spec)
    assert incident is not None

    injected = _by_cell(emit_rf(layout, spec, incident))
    quiet = _by_cell(_baseline(layout, spec))

    for cell, payload in injected.items():
        timestamp, sensor_id, channel_index = cell
        touched = (
            sensor_id in incident.sensors
            and channel_index in incident.channels
            and incident.start <= timestamp < incident.end
        )
        if not touched:
            assert payload == quiet[cell], cell


def test_the_snr_falls_where_the_power_rises(layout: RfLayout) -> None:
    # spec: scn-002
    # A raised floor is what a signal has to be heard over. Power and SNR
    # moving the same way would be a floor that improves reception.
    spec = _spec()
    incident = plan_incident(layout, spec)
    assert incident is not None

    injected = _by_cell(emit_rf(layout, spec, incident))
    quiet = _by_cell(_baseline(layout, spec))

    for cell, payload in injected.items():
        if payload["power_dbm"] > quiet[cell]["power_dbm"]:
            assert payload["snr_db"] < quiet[cell]["snr_db"]


# --------------------------------------------------------- rf-sensor-fault


def test_a_sensor_fault_affects_one_sensor(layout: RfLayout) -> None:
    # spec: scn-002, anom-007
    incident = plan_incident(layout, _spec(scenario_type=ScenarioType.RF_SENSOR_FAULT))
    assert incident is not None

    assert len(incident.sensors) == 1


def test_a_sensor_faults_spatial_neighbours_stay_nominal(layout: RfLayout) -> None:
    # spec: scn-002, anom-007
    # The signature the sensor-fault rule reads: abnormal here, nominal next
    # door. If a run raised the neighbours too, the rule would correctly
    # refuse to fire and the scenario would be unscoreable.
    spec = _spec(scenario_type=ScenarioType.RF_SENSOR_FAULT)
    incident = plan_incident(layout, spec)
    assert incident is not None

    injected = _by_cell(emit_rf(layout, spec, incident))
    quiet = _by_cell(_baseline(layout, spec))
    faulty = incident.sensors[0]

    for neighbour in layout.neighbours(faulty):
        for cell, payload in injected.items():
            if cell[1] == neighbour:
                assert payload == quiet[cell]


def test_a_sensor_fault_can_be_confined_to_one_channel_or_span_them_all(
    layout: RfLayout,
) -> None:
    # spec: scn-002, anom-007
    # Both patterns come from this one type, because anom-007 must report them
    # with different confidence: a lone deviation points at the receiver, one
    # across all eight points at the environment.
    narrow = plan_incident(
        layout,
        _spec(
            scenario_type=ScenarioType.RF_SENSOR_FAULT,
            incident=IncidentParameters(spectral_extent=SpectralExtent.NARROWBAND),
        ),
    )
    broad = plan_incident(
        layout,
        _spec(
            scenario_type=ScenarioType.RF_SENSOR_FAULT,
            incident=IncidentParameters(spectral_extent=SpectralExtent.BROADBAND),
        ),
    )
    assert narrow is not None and broad is not None

    assert len(narrow.channels) == 1
    assert len(broad.channels) == len(layout.channels)


# ------------------------------------------------------------- determinism


def test_the_same_seed_stages_the_same_incident(layout: RfLayout) -> None:
    # spec: scn-002, scn-001
    assert plan_incident(layout, _spec()) == plan_incident(layout, _spec())


def test_a_different_seed_stages_it_somewhere_else(layout: RfLayout) -> None:
    # spec: scn-002, scn-001
    # Without this, thirty runs in a batch stage the same incident in the same
    # place and the campaign has one data point.
    sites = {
        plan_incident(layout, _spec(seed=seed)).sensors  # type: ignore[union-attr]
        for seed in range(SEED, SEED + 12)
    }

    assert len(sites) > 1


def test_the_injected_stream_is_reproducible(layout: RfLayout) -> None:
    # spec: scn-002, scn-001
    assert _run(layout, _spec()) == _run(layout, _spec())


# ------------------------------------------------------------ ground truth


def test_the_ground_truth_records_what_was_staged(layout: RfLayout) -> None:
    # spec: scn-002
    spec = _spec()
    incident = plan_incident(layout, spec)
    assert incident is not None

    truth = ground_truth(spec, incident)

    assert truth["scenario_type"] == ScenarioType.GNSS_DEGRADATION.value
    assert truth["sensors"] == list(incident.sensors)
    assert truth["channels"] == list(incident.channels)
    assert truth["window"]["start"] == incident.start.isoformat()
    assert truth["window"]["end"] == incident.end.isoformat()
    assert truth["spectral_extent"] == SpectralExtent.NARROWBAND.value


def test_a_clean_run_still_records_a_ground_truth(layout: RfLayout) -> None:
    # spec: scn-002, anom-008
    # "Nothing was injected" is an answer, and the false-positive control needs
    # it stated rather than absent -- an absent record reads as "not recorded".
    spec = _spec(scenario_type=ScenarioType.NORMAL_BASELINE)

    truth = ground_truth(spec, None)

    assert truth["scenario_type"] == ScenarioType.NORMAL_BASELINE.value
    assert truth["sensors"] == []
    assert truth["channels"] == []
    assert truth["window"] is None


def test_no_record_carries_the_scenario_type_or_the_injection(
    layout: RfLayout,
) -> None:
    # spec: scn-002, api-009
    spec = _spec()
    injected = _run(layout, spec)[0]
    quiet = _baseline(layout, spec)[0]

    # Compared against the quiet run rather than searched for suspicious words.
    # The substring form of this test passes here only by luck -- an RF payload
    # happens to carry no field named like `on_ground`, which is what caught
    # the same assertion on the track side. An injection may change what a
    # field says; it may never add one.
    assert set(injected) == set(quiet)
    assert set(injected["payload"]) == set(quiet["payload"])
    assert "ground_truth" not in injected["payload"]


def test_an_injected_cell_is_labelled_the_same_as_a_quiet_one(
    layout: RfLayout,
) -> None:
    # spec: scn-002, api-009
    # The subtle half of the same rule. A signal_type of "interference" on
    # exactly the injected cells is the answer key written onto every record,
    # in a field both the detector and the analyst can read. The label must not
    # vary with what was staged.
    spec = _spec()
    incident = plan_incident(layout, spec)
    assert incident is not None

    labels = {
        record["payload"]["signal_type"] for record in emit_rf(layout, spec, incident)
    }

    assert len(labels) == 1
