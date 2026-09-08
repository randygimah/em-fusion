"""Scenario types, the track half. Spec: scn-002 (pass 2 of 3).

Pass 1 staged incidents on the invented RF grid. Two of the five types also
alter the *replayed* stream, which is real data, and that changes what the work
is: the RF side invents readings, this side edits recorded ones.

Two signatures, and the distinction between them is the whole reason `dal-001`
carries two staleness clocks rather than one:

* **`aircraft-coverage-gap` suppresses rows.** The aircraft stops being heard
  from. Both clocks go stale together, because nothing is arriving at all.
* **`gnss-degradation` freezes the position clock.** The aircraft keeps
  transmitting -- contact stays fresh -- while the position it reports stops
  advancing. That is the shape 4,553 rows of the real corpus already carry, and
  it is what makes the two types distinguishable rather than two names for one
  dropout.

**Perturbation sits between the adapter and the DAL.** `adp-001` is specified as
a pure windowed reader, so editing rows inside it would break a passing item;
`dal-003` owns provenance, so editing them after the DAL would mean rewriting
records that have already been validated and stamped. The seam is the replay
driver, which is the only place that already composes the two.

**Selection is keyed, not sampled.** Whether an aircraft is targeted is derived
from the seed and that aircraft's own identity, so the answer does not depend on
what order the corpus arrives in, on how the replay is batched, or on how many
aircraft have been seen so far -- the same argument `scn-001` made for the RF
grid, applied to a stream this time.

**The exclusion list is honoured here or nowhere.** `adp-008` names the tracks
that already carry a natural gap; staging a gap on one of those produces a run
whose ground truth and whose data disagree, and a false-positive rate for the
type that means nothing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.dal.pseudonymise import Pseudonymiser
from app.scenario.emitter import BaselineParameters, RunSpec
from app.scenario.incident import IncidentParameters, ScenarioType, ground_truth
from app.scenario.tracks import (
    TrackMode,
    TrackPerturber,
    load_exclusions,
    plan_track_perturbation,
)

PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")

SEED = 20220627
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
DURATION_SECONDS = 900
OFFSET_S = 120
WINDOW_S = 300

#: Inside the staged window, and outside it on both sides. Written as offsets
#: from the run start so the three move together if the window does.
DURING = START + timedelta(seconds=OFFSET_S + 10)
BEFORE = START + timedelta(seconds=OFFSET_S - 10)
AFTER = START + timedelta(seconds=OFFSET_S + WINDOW_S + 10)


def _spec(
    *,
    scenario_type: ScenarioType = ScenarioType.AIRCRAFT_COVERAGE_GAP,
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


def _record(
    *,
    icao24: str = "4d22ec",
    at: datetime = DURING,
    position_staleness_s: float = 1.06,
    contact_staleness_s: float = 0.0,
) -> dict[str, Any]:
    """One track source record, in the shape the OpenSky adapter emits.

    Still carrying `icao24`: perturbation happens before the DAL, which is the
    only place the real identifier exists at all.
    """
    return {
        "source_id": "opensky-replay",
        "source_type": "opensky",
        "observation_type": "track",
        "timestamp": at,
        "location": {"lat": 51.0905, "lon": 7.5473},
        "payload": {
            "icao24": icao24,
            "callsign": "CXI27NM ",
            "altitude_m": 5753.1,
            "velocity_ms": 194.26,
            "heading_deg": 135.64,
            "vertical_rate_ms": 13.33,
            "on_ground": False,
            "position_staleness_s": position_staleness_s,
            "contact_staleness_s": contact_staleness_s,
        },
    }


def _perturber(
    spec: RunSpec, *, excluded: frozenset[str] = frozenset()
) -> TrackPerturber:
    perturbation = plan_track_perturbation(spec)
    assert perturbation is not None
    return TrackPerturber(perturbation, pseudonymiser=PSEUDONYMISER, excluded=excluded)


def _targeted_aircraft(spec: RunSpec, count: int = 200) -> set[str]:
    """Which of a synthetic fleet this run would touch."""
    perturber = _perturber(spec)
    return {
        f"{index:06x}" for index in range(count) if perturber.targets(f"{index:06x}")
    }


# ------------------------------------------------------- which types perturb


def test_normal_baseline_perturbs_no_track() -> None:
    # spec: scn-002, anom-008
    assert (
        plan_track_perturbation(_spec(scenario_type=ScenarioType.NORMAL_BASELINE))
        is None
    )


def test_a_sensor_fault_perturbs_no_track() -> None:
    # spec: scn-002, anom-007
    # A faulty receiver says nothing about the aircraft it is listening to. If
    # this staged a track effect too, the sensor-fault rule and the fusion rule
    # would both fire and the scenario would stop being a single-cause case.
    assert (
        plan_track_perturbation(_spec(scenario_type=ScenarioType.RF_SENSOR_FAULT))
        is None
    )


def test_a_coverage_gap_suppresses_and_gnss_degradation_freezes() -> None:
    # spec: scn-002
    gap = plan_track_perturbation(
        _spec(scenario_type=ScenarioType.AIRCRAFT_COVERAGE_GAP)
    )
    gnss = plan_track_perturbation(_spec(scenario_type=ScenarioType.GNSS_DEGRADATION))
    assert gap is not None and gnss is not None

    assert gap.mode is TrackMode.SUPPRESS
    assert gnss.mode is TrackMode.FREEZE


# ------------------------------------------------------------- suppression


def test_a_targeted_aircraft_vanishes_inside_the_window() -> None:
    # spec: scn-002
    spec = _spec()
    perturber = _perturber(spec)
    target = next(iter(_targeted_aircraft(spec)))

    assert perturber.apply(_record(icao24=target, at=DURING)) is None


def test_a_targeted_aircraft_reports_normally_outside_the_window() -> None:
    # spec: scn-002
    # The gap has to end, or the aircraft has simply left the corpus and the
    # detector has no "after" to compare against.
    spec = _spec()
    perturber = _perturber(spec)
    target = next(iter(_targeted_aircraft(spec)))

    for moment in (BEFORE, AFTER):
        record = _record(icao24=target, at=moment)
        assert perturber.apply(record) == record


def test_an_untargeted_aircraft_is_never_touched() -> None:
    # spec: scn-002
    spec = _spec()
    perturber = _perturber(spec)
    untargeted = next(
        identifier
        for identifier in (f"{index:06x}" for index in range(500))
        if not perturber.targets(identifier)
    )

    record = _record(icao24=untargeted, at=DURING)
    assert perturber.apply(record) == record


# ------------------------------------------------------------- the freeze


def test_a_frozen_position_goes_stale_while_contact_stays_fresh() -> None:
    # spec: scn-002, dal-001
    # The GNSS signature, and the reason two clocks are carried. Both stale is
    # a dropout; fresh contact with a stale position is degradation.
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    perturber = _perturber(spec)
    target = next(iter(_targeted_aircraft(spec)))

    record = perturber.apply(_record(icao24=target, at=DURING))
    assert record is not None

    assert record["payload"]["position_staleness_s"] > 10.0
    assert record["payload"]["contact_staleness_s"] == 0.0


def test_the_frozen_position_grows_staler_as_the_window_runs() -> None:
    # spec: scn-002
    # A constant staleness is a constant, not a degradation: a rolling-average
    # detector would see a step and then nothing.
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    perturber = _perturber(spec)
    target = next(iter(_targeted_aircraft(spec)))

    early = perturber.apply(
        _record(icao24=target, at=START + timedelta(seconds=OFFSET_S + 10))
    )
    late = perturber.apply(
        _record(icao24=target, at=START + timedelta(seconds=OFFSET_S + 200))
    )
    assert early is not None and late is not None

    assert (
        late["payload"]["position_staleness_s"]
        > early["payload"]["position_staleness_s"]
    )


def test_a_freeze_never_drops_a_record() -> None:
    # spec: scn-002
    # The two signatures must stay distinguishable: a freeze that also dropped
    # rows would be a coverage gap wearing a different name.
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    perturber = _perturber(spec)
    target = next(iter(_targeted_aircraft(spec)))

    assert perturber.apply(_record(icao24=target, at=DURING)) is not None


# --------------------------------------------------------- the exclusion list


def test_an_excluded_aircraft_is_never_targeted() -> None:
    # spec: scn-002, adp-008
    # The reason adp-008 exists. Staging a gap on a track that already carries
    # one makes the ground truth and the data disagree.
    spec = _spec()
    targeted = next(iter(_targeted_aircraft(spec)))
    pseudonym = PSEUDONYMISER.aircraft(targeted)
    assert pseudonym is not None

    guarded = _perturber(spec, excluded=frozenset({pseudonym}))

    assert not guarded.targets(targeted)
    record = _record(icao24=targeted, at=DURING)
    assert guarded.apply(record) == record


def test_the_exclusion_list_is_read_from_the_committed_artefact(
    tmp_path: Path,
) -> None:
    # spec: scn-002, adp-008
    path = tmp_path / "natural_gaps.json"
    path.write_text(
        json.dumps(
            {
                "min_gap_s": 20,
                "gaps": [
                    {"aircraft_id": "AC-aaa", "start": 1, "end": 2, "duration_s": 1},
                    {"aircraft_id": "AC-aaa", "start": 5, "end": 9, "duration_s": 4},
                    {"aircraft_id": "AC-bbb", "start": 1, "end": 3, "duration_s": 2},
                ],
            }
        )
    )

    # Two entries for one aircraft is one excluded aircraft: the list excludes
    # tracks, not gaps, which is exactly the conflation that put the confound
    # at 1.05% instead of 0.74%.
    assert load_exclusions(path) == frozenset({"AC-aaa", "AC-bbb"})


def test_a_missing_exclusion_list_is_refused_rather_than_ignored(
    tmp_path: Path,
) -> None:
    # spec: scn-002, adp-008
    # An empty set read from an absent file is the mitigation silently not
    # applying, which looks identical to it applying and finding nothing.
    with pytest.raises(FileNotFoundError):
        load_exclusions(tmp_path / "absent.json")


# ------------------------------------------------------------- determinism


def test_the_same_seed_targets_the_same_aircraft() -> None:
    # spec: scn-002, scn-001
    assert _targeted_aircraft(_spec()) == _targeted_aircraft(_spec())


def test_a_different_seed_targets_different_aircraft() -> None:
    # spec: scn-002, scn-001
    assert _targeted_aircraft(_spec()) != _targeted_aircraft(_spec(seed=SEED + 1))


def test_selection_does_not_depend_on_the_order_rows_arrive_in() -> None:
    # spec: scn-002, scn-001
    # The leak this design exists to close. A sampler that took the first n
    # aircraft it saw, or drew from a generator as rows streamed past, would
    # target a different set when the replay was batched differently -- and the
    # ground truth would still claim the first set.
    spec = _spec()
    forward = _perturber(spec)
    backward = _perturber(spec)
    fleet = [f"{index:06x}" for index in range(200)]

    ahead = {identifier for identifier in fleet if forward.targets(identifier)}
    behind = {
        identifier for identifier in reversed(fleet) if backward.targets(identifier)
    }

    assert ahead == behind
    assert ahead


def test_some_but_not_all_of_a_fleet_is_targeted() -> None:
    # spec: scn-002
    # Targeting everything is an outage, not an incident, and leaves no
    # unaffected traffic to judge the affected traffic against.
    targeted = _targeted_aircraft(_spec())

    assert 0 < len(targeted) < 200


# ------------------------------------------------------------ ground truth


def test_the_ground_truth_names_the_aircraft_that_were_touched() -> None:
    # spec: scn-002
    spec = _spec()
    perturber = _perturber(spec)
    target = next(iter(_targeted_aircraft(spec)))
    perturber.apply(_record(icao24=target, at=DURING))

    truth = ground_truth(spec, None, perturber)

    assert truth["track_mode"] == TrackMode.SUPPRESS.value
    assert PSEUDONYMISER.aircraft(target) in truth["aircraft"]


def test_the_ground_truth_names_aircraft_by_pseudonym_only() -> None:
    # spec: scn-002, api-009, dal-004
    # The answer key is stored beside the run, and the run record is readable.
    # A real aircraft address in it would put source identity in the database
    # by the back door.
    spec = _spec()
    perturber = _perturber(spec)
    target = next(iter(_targeted_aircraft(spec)))
    perturber.apply(_record(icao24=target, at=DURING))

    truth = ground_truth(spec, None, perturber)

    assert target not in json.dumps(truth)
    assert all(name.startswith("AC-") for name in truth["aircraft"])


def test_a_perturbed_record_carries_no_trace_of_the_scenario() -> None:
    # spec: scn-002, api-009
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    perturber = _perturber(spec)
    target = next(iter(_targeted_aircraft(spec)))

    untouched = _record(icao24=target, at=BEFORE)
    record = perturber.apply(_record(icao24=target, at=DURING))
    assert record is not None

    # Compared against an unperturbed record rather than searched for
    # suspicious words. The first version of this test asked whether any key
    # contained "ground", which matches `on_ground` -- a legitimate field about
    # whether the aircraft is airborne, and nothing to do with ground truth.
    # A perturbation may change what a field says; it may never add a field.
    assert set(record) == set(untouched)
    assert set(record["payload"]) == set(untouched["payload"])
    assert "ground_truth" not in record["payload"]


# ------------------------------------------------------------- the seam


def test_replay_window_applies_a_transform_and_honours_a_drop(
    tmp_path: Path,
) -> None:
    """The seam perturbation runs in. Spec: scn-002.

    Asserted through the real composition rather than by calling the perturber
    directly: the claim is that a perturbation actually reaches the DAL on the
    replay path, and a transform the driver forgot to pass would leave every
    unit test in this file green.
    """
    # spec: scn-002, adp-001
    from app.adapters.opensky import Window, replay_window
    from app.corpus.extract import write_parquet
    from app.dal.models import DataMode
    from app.dal.validation import IngestContext
    from tests.fakes import InMemoryObservationRepository
    from tests.test_adp_opensky import _row

    path = tmp_path / "extract.parquet"
    write_parquet([_row(0), _row(10), _row(20)], path)
    repository = InMemoryObservationRepository()

    result = replay_window(
        path,
        Window(
            start=datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC),
            end=datetime(2022, 6, 27, 12, 1, 0, tzinfo=UTC),
        ),
        IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=1),
        repository,
        PSEUDONYMISER,
        transform=lambda record: None if record["timestamp"].second == 10 else record,
    )

    # Three rows read, one suppressed: a dropped record is gone, not
    # quarantined. Quarantine means "this record was wrong"; a staged gap means
    # the aircraft was never heard, and the two must not be confused.
    assert result.accepted == 2
    assert result.quarantined == 0
    assert len(repository.observations) == 2
