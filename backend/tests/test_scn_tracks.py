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
from app.scenario.incident import (
    IncidentParameters,
    ScenarioType,
    centre_sensor_id,
    ground_truth,
)
from app.scenario.layout import load_layout
from app.scenario.seeding import derive_unit
from app.scenario.tracks import (
    TrackMode,
    TrackPerturber,
    load_exclusions,
    plan_track_perturbation,
    select_targets,
)

PSEUDONYMISER = Pseudonymiser(seed="a-test-seed-not-the-real-one")

LAYOUT = load_layout()

SEED = 20220627
START = datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC)
DURATION_SECONDS = 900
OFFSET_S = 120
WINDOW_S = 300

#: Inside the staged window, and outside it on both sides. Written as offsets
#: from the run start so the three move together if the window does.
DURING = START + timedelta(seconds=OFFSET_S + 10)

#: Inside the staged zone. Pass 3 added the spatial axis the spec always
#: called for -- "aircraft inside the affected area" -- so a record has to be
#: somewhere the incident reaches before anything happens to it. These fixtures
#: previously sat near Koln-Bonn, which the zone for this seed excludes.
_CENTRE = LAYOUT.site(centre_sensor_id(LAYOUT, SEED))
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
    lat: float = _CENTRE.lat,
    lon: float = _CENTRE.lon,
    on_ground: bool = False,
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
        "location": {"lat": lat, "lon": lon},
        "payload": {
            "icao24": icao24,
            "callsign": "CXI27NM ",
            "altitude_m": 5753.1,
            "velocity_ms": 194.26,
            "heading_deg": 135.64,
            "vertical_rate_ms": 13.33,
            "on_ground": on_ground,
            "position_staleness_s": position_staleness_s,
            "contact_staleness_s": contact_staleness_s,
        },
    }


def _perturber(
    spec: RunSpec, *, excluded: frozenset[str] = frozenset()
) -> TrackPerturber:
    perturbation = plan_track_perturbation(LAYOUT, spec)
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
        plan_track_perturbation(
            LAYOUT, _spec(scenario_type=ScenarioType.NORMAL_BASELINE)
        )
        is None
    )


def test_a_sensor_fault_perturbs_no_track() -> None:
    # spec: scn-002, anom-007
    # A faulty receiver says nothing about the aircraft it is listening to. If
    # this staged a track effect too, the sensor-fault rule and the fusion rule
    # would both fire and the scenario would stop being a single-cause case.
    assert (
        plan_track_perturbation(
            LAYOUT, _spec(scenario_type=ScenarioType.RF_SENSOR_FAULT)
        )
        is None
    )


def test_a_coverage_gap_suppresses_and_gnss_degradation_freezes() -> None:
    # spec: scn-002
    gap = plan_track_perturbation(
        LAYOUT, _spec(scenario_type=ScenarioType.AIRCRAFT_COVERAGE_GAP)
    )
    gnss = plan_track_perturbation(
        LAYOUT, _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    )
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


# --------------------------------------------------- staging only on flight
#
# Spec: scn-006. The targeting asked one question -- is this inside the zone --
# and an aircraft parked at an airfield inside it was targeted like one flying
# through. Measured across 77 staged runs, **209 of 381 aircraft the answer key
# called staged were on the ground for every report of the run**: 55 per cent
# of every injection landed where nothing could be detected.
#
# `anom-010` then refuses them, correctly, because an aircraft on the ground
# stopped reporting when it was switched off and its stale position is
# indistinguishable from that. Both components behave as specified and the
# combination guarantees a false negative, which is why the fix goes in the
# targeting rather than in the metrics.


def _targeted_icao(spec: RunSpec, count: int = 200) -> str:
    """An identifier this run would actually stage on."""
    perturber = _perturber(spec)
    for index in range(count):
        if perturber.targets(f"{index:06x}"):
            return f"{index:06x}"
    raise AssertionError("this run targets nothing in the synthetic fleet")


def test_a_record_from_an_aircraft_on_the_ground_is_left_alone() -> None:
    """The record passes every other gate -- in the window, inside the zone,
    drawn as a target -- and is still untouched."""
    # spec: scn-006
    spec = _spec()
    perturber = _perturber(spec)
    icao = _targeted_icao(spec)

    grounded = perturber.apply(_record(icao24=icao, on_ground=True))

    assert grounded == _record(icao24=icao, on_ground=True)


def test_an_aircraft_on_the_ground_never_reaches_the_answer_key() -> None:
    """The half that matters. A parked aircraft left in the key is a
    guaranteed false negative in `eval-002`, and filtering it out afterwards
    would leave the perturbed record in the run with nothing naming it."""
    # spec: scn-006, scn-002, eval-002
    spec = _spec()
    perturber = _perturber(spec)
    icao = _targeted_icao(spec)

    perturber.apply(_record(icao24=icao, on_ground=True))

    assert perturber.affected == frozenset()


def test_the_same_aircraft_is_staged_on_once_it_is_flying() -> None:
    """An aircraft airborne for part of the window is eligible for that part.
    It is detectable while it was flying, so excluding it wholesale would trade
    one bias for another."""
    # spec: scn-006
    spec = _spec(scenario_type=ScenarioType.GNSS_DEGRADATION)
    perturber = _perturber(spec)
    icao = _targeted_icao(spec)

    perturber.apply(_record(icao24=icao, on_ground=True))
    assert perturber.affected == frozenset()

    airborne = perturber.apply(_record(icao24=icao, on_ground=False))

    assert airborne is not None
    assert airborne["payload"]["position_staleness_s"] > 1.06
    assert len(perturber.affected) == 1


def test_suppression_does_not_remove_a_grounded_record() -> None:
    """`aircraft-coverage-gap` stages by suppressing rows. Suppressing a parked
    aircraft's rows would stage a disruption on something that cannot be
    disrupted, and the answer key would not name it."""
    # spec: scn-006, scn-002
    spec = _spec(scenario_type=ScenarioType.AIRCRAFT_COVERAGE_GAP)
    perturber = _perturber(spec)
    icao = _targeted_icao(spec)

    assert perturber.apply(_record(icao24=icao, on_ground=True)) is not None
    assert perturber.apply(_record(icao24=icao, on_ground=False)) is None


# ---------------------------------------------------------------------------
# scn-007: a run that stages on nothing has no answer key.
#
# Once scn-006 restricted staging to aircraft in flight, the eligible pool
# shrank and the 8 per cent draw began yielding a mean of 1.7 aircraft per
# run, with 11 of 40 drawing none at all. A run with an empty answer key is
# indistinguishable from its own control by construction, so a quarter of the
# coverage-gap arm could not be scored on.
#
# The floor cannot be applied where selection happens. scn-002's seam is a
# per-record transform on a stream, and ranking a pool needs the pool -- so
# the run surveys its window first, ranks what it finds, and hands the chosen
# set to the perturber. These tests fix that split: the survey decides, the
# perturber obeys, and the two agree on what "eligible" means because they
# ask the same object.
#
# The floor's value is not asserted here. It is measured by
# backend/measurements/corpus/scn007_floor.py.
# ---------------------------------------------------------------------------


def _pool(count: int, **kwargs: Any) -> list[dict[str, Any]]:
    """`count` distinct aircraft, each with one eligible record."""
    return [
        _record(icao24=f"{0x400000 + i:06x}", **kwargs)  # noqa: E231
        for i in range(count)
    ]


def _selection(records: list[dict[str, Any]], *, minimum: int, seed: int = SEED):
    perturbation = plan_track_perturbation(LAYOUT, _spec(seed=seed))
    assert perturbation is not None
    return select_targets(
        perturbation, records, pseudonymiser=PSEUDONYMISER, minimum=minimum
    )


def test_a_large_pool_takes_the_fractions_count_and_the_floor_does_nothing() -> None:
    # spec: scn-007
    # 8 per cent of 200 is 16, comfortably past a floor of 3, so the floor
    # must not alter what the fraction would have done.
    selection = _selection(_pool(200), minimum=3)
    assert selection.eligible == 200
    assert selection.requested == 16
    assert len(selection.chosen) == 16
    assert selection.floor_reached is True


def test_a_pool_the_fraction_would_underfill_is_raised_to_the_floor() -> None:
    # spec: scn-007
    # 8 per cent of 20 is 1.6 -- the case that produced a mean of 1.7.
    selection = _selection(_pool(20), minimum=4)
    assert selection.requested == 4
    assert len(selection.chosen) == 4
    assert selection.floor_reached is True


def test_a_pool_smaller_than_the_floor_stages_all_of_it_and_says_so() -> None:
    # spec: scn-007
    # The item's own failure case inverted: staging fewer silently would
    # reintroduce the empty answer key this item exists to remove, so the
    # shortfall is recorded rather than hidden.
    selection = _selection(_pool(2), minimum=5)
    assert selection.eligible == 2
    assert len(selection.chosen) == 2
    assert selection.floor_reached is False


def test_an_empty_pool_stages_nothing_and_reports_the_floor_unreached() -> None:
    # spec: scn-007
    selection = _selection([], minimum=5)
    assert selection.chosen == frozenset()
    assert selection.eligible == 0
    assert selection.floor_reached is False


def test_the_selection_does_not_depend_on_the_order_records_arrive_in() -> None:
    # spec: scn-007, scn-001, NFR-601
    # The property the original per-aircraft draw had for free and a
    # draw-until-N loop would have destroyed.
    records = _pool(60)
    forwards = _selection(records, minimum=3)
    backwards = _selection(list(reversed(records)), minimum=3)
    assert forwards.chosen == backwards.chosen


def test_the_selection_is_reproducible_from_the_seed_alone() -> None:
    # spec: scn-007, scn-001
    records = _pool(60)
    assert _selection(records, minimum=3).chosen == _selection(
        records, minimum=3
    ).chosen


def test_a_different_seed_chooses_a_different_set() -> None:
    # spec: scn-007
    # Otherwise the floor would stage the same aircraft every run, and the
    # arm would carry one repeated experiment rather than forty.
    records = _pool(60)
    assert _selection(records, minimum=3).chosen != _selection(
        records, minimum=3, seed=SEED + 1
    ).chosen


def test_an_aircraft_on_the_ground_is_not_eligible() -> None:
    # spec: scn-007, scn-006
    # The survey has to agree with the perturber about what may be staged
    # on, or the answer key names aircraft nothing was done to.
    selection = _selection(_pool(20, on_ground=True), minimum=5)
    assert selection.eligible == 0
    assert selection.chosen == frozenset()


def test_an_aircraft_outside_the_window_is_not_eligible() -> None:
    # spec: scn-007, scn-002
    selection = _selection(_pool(20, at=BEFORE), minimum=5)
    assert selection.eligible == 0


def test_an_aircraft_outside_the_zone_is_not_eligible() -> None:
    # spec: scn-007, scn-002
    selection = _selection(_pool(20, lat=0.0, lon=0.0), minimum=5)
    assert selection.eligible == 0


def test_an_excluded_aircraft_is_not_eligible() -> None:
    # spec: scn-007, adp-008
    # Refused before the ranking, not after: an exclusion applied afterwards
    # would let the floor pull in a track adp-008 removed.
    records = _pool(20)
    perturbation = plan_track_perturbation(LAYOUT, _spec())
    assert perturbation is not None
    every = frozenset(
        PSEUDONYMISER.aircraft(r["payload"]["icao24"]) or "" for r in records
    )
    selection = select_targets(
        perturbation,
        records,
        pseudonymiser=PSEUDONYMISER,
        excluded=every,
        minimum=5,
    )
    assert selection.eligible == 0


def test_one_aircraft_with_many_records_is_counted_once() -> None:
    # spec: scn-007
    # Eligibility is per record and selection is per aircraft; counting
    # records would let a frequently-reported aircraft fill the floor alone.
    records = [_record(icao24="4d22ec") for _ in range(30)]
    selection = _selection(records, minimum=2)
    assert selection.eligible == 1
    assert len(selection.chosen) == 1


def test_a_perturber_given_a_selection_stages_on_exactly_that_set() -> None:
    # spec: scn-007
    records = _pool(60)
    perturbation = plan_track_perturbation(LAYOUT, _spec())
    assert perturbation is not None
    selection = select_targets(
        perturbation, records, pseudonymiser=PSEUDONYMISER, minimum=6
    )
    perturber = TrackPerturber(
        perturbation, pseudonymiser=PSEUDONYMISER, selection=selection
    )
    for record in records:
        perturber.apply(record)
    assert perturber.affected == selection.chosen


def test_a_perturber_with_no_selection_keeps_the_unbounded_behaviour() -> None:
    # spec: scn-007
    # Not a fallback pretending to be the new rule: it is the fraction with
    # no floor, which is what the perturber did before this item and what it
    # still means when no pool has been surveyed.
    records = _pool(60)
    perturbation = plan_track_perturbation(LAYOUT, _spec())
    assert perturbation is not None
    perturber = TrackPerturber(perturbation, pseudonymiser=PSEUDONYMISER)
    for record in records:
        perturber.apply(record)
    expected = {
        p
        for record in records
        if (p := PSEUDONYMISER.aircraft(record["payload"]["icao24"])) is not None
        and perturber.targets(record["payload"]["icao24"])
    }
    assert perturber.affected == expected


def test_a_floor_of_zero_is_legal_but_is_not_the_old_behaviour() -> None:
    # spec: scn-007
    # Worth stating because it caught me out: a floor of zero does NOT
    # restore the pre-scn-007 rule. The old rule thresholded each aircraft's
    # own derived value at the fraction, which on a small pool sometimes
    # drew one; ranking takes `round(fraction * pool)`, which on a small
    # pool is deterministically zero. So a floor of zero is strictly worse
    # than what came before, and the floor must be at least one for this
    # item to be an improvement in every case rather than on average.
    selection = _selection(_pool(20), minimum=0)
    assert selection.requested == 2  # 8 per cent of 20, rounded
    assert selection.floor_reached is True

    tiny = _selection(_pool(5), minimum=0)
    assert tiny.requested == 0
    assert tiny.chosen == frozenset()


def test_a_negative_floor_is_refused() -> None:
    # spec: scn-007
    with pytest.raises(ValueError, match="minimum"):
        _selection(_pool(20), minimum=-1)


def test_the_answer_key_records_what_the_survey_found() -> None:
    # spec: scn-007, eval-002
    # A run that staged two because only two were there is a different fact
    # from one that staged two because two were asked for, and the aircraft
    # list alone cannot tell them apart.
    records = _pool(2)
    spec = _spec()
    perturbation = plan_track_perturbation(LAYOUT, spec)
    assert perturbation is not None
    selection = select_targets(
        perturbation, records, pseudonymiser=PSEUDONYMISER, minimum=5
    )
    perturber = TrackPerturber(
        perturbation, pseudonymiser=PSEUDONYMISER, selection=selection
    )
    for record in records:
        perturber.apply(record)
    truth = ground_truth(spec, None, perturber)
    assert truth["aircraft_eligible"] == 2
    assert truth["aircraft_requested"] == 5
    assert truth["aircraft_floor_reached"] is False


# --- four tests added after a mutation pass found the gaps they close ------


def test_the_chosen_set_is_the_lowest_derived_values_under_this_seed() -> None:
    # spec: scn-007, scn-001
    # Found by mutation: both "rank by nothing, take the set's own order" and
    # "rank by pseudonym, ignoring the seed" survived every test above. The
    # order-independence test could not see them because a small set of
    # strings iterates the same way whatever order it was built in, and the
    # different-seed test could not either, because changing the seed also
    # moves the zone centre and so changes the pool. This holds the pool and
    # the seed fixed and pins the ranking itself.
    records = _pool(50)
    perturbation = plan_track_perturbation(LAYOUT, _spec())
    assert perturbation is not None
    selection = select_targets(
        perturbation, records, pseudonymiser=PSEUDONYMISER, minimum=7
    )

    eligible = {
        p
        for record in records
        if (p := PSEUDONYMISER.aircraft(record["payload"]["icao24"])) is not None
    }
    expected = sorted(
        eligible, key=lambda p: (derive_unit(SEED, "track-target", p), p)
    )[:7]
    assert selection.chosen == frozenset(expected)

    # And the chosen are strictly below every unchosen one, which is what
    # "the lowest n" means and what an arbitrary order would not give.
    chosen_values = {derive_unit(SEED, "track-target", p) for p in selection.chosen}
    rest = {derive_unit(SEED, "track-target", p) for p in eligible - selection.chosen}
    assert max(chosen_values) < min(rest)


def test_a_pool_exactly_the_size_of_the_floor_has_reached_it() -> None:
    # spec: scn-007
    # Found by mutation: `>` passed every test because none sat on the
    # boundary. The boundary belongs to the configured value, as it does for
    # anom-014's minimum duration and anom-001's bands.
    assert _selection(_pool(5), minimum=5).floor_reached is True
    assert _selection(_pool(4), minimum=5).floor_reached is False


def test_the_floor_stages_more_than_the_fraction_alone_would_have() -> None:
    # spec: scn-007
    # Found by mutation: a perturber that ignored its selection entirely and
    # fell back to the fraction survived, because on that pool the two sets
    # happened to coincide. Here they cannot: 8 per cent of 20 is 2, and the
    # floor asks for 8.
    records = _pool(20)
    perturbation = plan_track_perturbation(LAYOUT, _spec())
    assert perturbation is not None
    selection = select_targets(
        perturbation, records, pseudonymiser=PSEUDONYMISER, minimum=8
    )
    assert len(selection.chosen) == 8

    perturber = TrackPerturber(
        perturbation, pseudonymiser=PSEUDONYMISER, selection=selection
    )
    for record in records:
        perturber.apply(record)
    assert perturber.affected == selection.chosen

    unbounded = TrackPerturber(perturbation, pseudonymiser=PSEUDONYMISER)
    fraction_only = {
        p
        for record in records
        if (p := PSEUDONYMISER.aircraft(record["payload"]["icao24"])) is not None
        and unbounded.targets(record["payload"]["icao24"])
    }
    assert len(fraction_only) < 8
    assert perturber.affected != fraction_only


def test_the_floor_does_not_lower_what_the_fraction_asked_for() -> None:
    # spec: scn-007
    # The floor is a floor and never a ceiling: where the fraction already
    # exceeds it the fraction wins, or a large pool would be capped at the
    # minimum and the arm would lose the traffic it was meant to carry.
    selection = _selection(_pool(400), minimum=5)
    assert selection.requested == 32
    assert len(selection.chosen) == 32
