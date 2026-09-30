"""Detection metrics over a scored corpus. Spec: eval-002.

**Recall is indexed by truth and precision by prediction**, which is the
constraint most of this file is about. Recall's denominator is the runs of a
scenario type; precision's is the runs *given* an anomaly type. A table row
carrying both under one label puts two denominators under one name, and they
coincide only where no arm is ever reported as another -- a result to state,
not an assumption to build on. So the arm rows and the type rows are separate
objects here, and nothing joins them but `f1`, which exists only where one
arm maps to one type.

**The word recall means two different things in this project** and they
differ by more than twenty points: `anom-011` measures it per staged
aircraft on the track side, this item measures it per run over reportable
output. The guard is mechanical rather than editorial -- no key in the
exported JSON is a bare `recall`, so neither figure can be quoted without
its denominator, and the two are never averaged.

**A wrong answer is two errors.** `anom-013` gives at most one claim per
zone, so a run reported as the wrong type is a false negative for the type
staged and a false positive for the type claimed. Three independent binary
tests would count that run once and lose half of it, which is why the
classification here is one multi-class confusion.

**There are two false-positive rates and they are never pooled.** A report
on `normal-baseline` is invention from nothing; a report on
`aircraft-coverage-gap` is cross-modal leakage, something real on the track
side reaching a radio verdict. Both arms are silent arms and they fail in
different ways, so one figure over 120 runs cannot say which failed.

**Latency is conditional on detection.** It exists only over the runs that
produced the right claim, and printed beside a recall below one it reads as
a property of the arm when it is a property of the successes.

**A rate over an empty population is `None`, never 0.0** -- `eval-005`'s
convention, which is also this item's named divide-by-zero failure case.

Nothing here touches a database. The outcomes arrive as the caller has
already read them, which is the shape the rest of `app/evaluation` uses.
"""

from __future__ import annotations

import json

import pytest

from app.detection.control import (
    REGISTER,
    SOURCE_GAP_RULE,
    SOURCE_GAP_TYPE,
    Control,
    Producer,
    audit,
    build_register,
)
from app.evaluation.metrics import (
    SILENT,
    ArmKind,
    DetectionMetrics,
    MetricsError,
    NegativeArm,
    RunOutcome,
    TrackSideRecall,
    TypePrecision,
    compute,
)

FAULT = "possible_sensor_fault"
INTERFERENCE = "possible_interference_zone"
SOURCE_GAP = SOURCE_GAP_TYPE

BASELINE = "normal-baseline"
GNSS = "gnss-degradation"
SENSOR_FAULT = "rf-sensor-fault"
COVERAGE_GAP = "aircraft-coverage-gap"
AMBIGUOUS = "ambiguous-mixed-evidence"


def _counts(register=REGISTER) -> dict[tuple[str, str], int]:
    """A quiet run's account of every built producer, inside every band.

    Built from the register rather than typed out, so a test register with a
    different membership needs no second copy of this.
    """
    counts: dict[tuple[str, str], int] = {}
    for key, producer in register.items():
        if not producer.built:
            continue
        band = producer.background
        counts[key] = band.low if band is not None else 0
    return counts


def _clean(run_id: str, register=REGISTER) -> Control:
    return audit(
        run_id=run_id,
        scenario_type=BASELINE,
        counts=_counts(register),
        register=register,
    )


def _leaking(run_id: str, register=REGISTER) -> Control:
    """A quiet run on which a reportable rule fired -- the control fails."""
    counts = _counts(register)
    counts[("SENSOR-FAULT", FAULT)] = 1
    return audit(
        run_id=run_id, scenario_type=BASELINE, counts=counts, register=register
    )


def _corpus() -> tuple[list[RunOutcome], dict[str, Control]]:
    """A small corpus decided correctly on every arm.

    Two runs per arm, which is enough for every denominator here to be
    distinguishable from every other and small enough to hand-check.
    """
    outcomes = [
        RunOutcome(run_id="b1", scenario_type=BASELINE, staged=False),
        RunOutcome(run_id="b2", scenario_type=BASELINE, staged=False),
        RunOutcome(run_id="c1", scenario_type=COVERAGE_GAP),
        RunOutcome(run_id="c2", scenario_type=COVERAGE_GAP),
        RunOutcome(
            run_id="g1",
            scenario_type=GNSS,
            reported=(INTERFERENCE,),
            latency_seconds=40.0,
        ),
        RunOutcome(
            run_id="g2",
            scenario_type=GNSS,
            reported=(INTERFERENCE,),
            latency_seconds=60.0,
        ),
        RunOutcome(
            run_id="f1",
            scenario_type=SENSOR_FAULT,
            reported=(FAULT,),
            latency_seconds=20.0,
        ),
        RunOutcome(
            run_id="f2",
            scenario_type=SENSOR_FAULT,
            reported=(FAULT,),
            latency_seconds=30.0,
        ),
        RunOutcome(run_id="a1", scenario_type=AMBIGUOUS, reported=(FAULT,)),
        RunOutcome(run_id="a2", scenario_type=AMBIGUOUS, reported=(FAULT,)),
    ]
    controls = {"b1": _clean("b1"), "b2": _clean("b2")}
    return outcomes, controls


def _computed() -> DetectionMetrics:
    outcomes, controls = _corpus()
    return compute(outcomes, controls=controls)


# --- the two recalls -------------------------------------------------------


def test_no_figure_is_exported_as_a_bare_recall() -> None:
    # spec: eval-002
    # The project holds two recalls with different denominators, so the word
    # alone identifies nothing. Enforced over the whole export rather than
    # over one row, because a second one would arrive in a new row.
    metrics = _computed()
    exported = json.loads(json.dumps(metrics.as_json()))

    def keys(node: object) -> list[str]:
        if isinstance(node, dict):
            found = list(node)
            for value in node.values():
                found += keys(value)
            return found
        if isinstance(node, list):
            return [k for item in node for k in keys(item)]
        return []

    every = keys(exported)
    assert "recall" not in every
    assert "recall_per_run" in every
    named = [k for k in every if "recall" in k]
    assert named and all(
        k.endswith("_per_run") or k.endswith("_per_staged_aircraft") for k in named
    )


def test_the_track_side_recall_is_carried_beside_the_run_level_one() -> None:
    # spec: eval-002, anom-011
    # anom-011's figure is per staged aircraft and this item's is per run.
    # Both are reported; neither is averaged into the other.
    outcomes, controls = _corpus()
    metrics = compute(
        outcomes,
        controls=controls,
        track_side={GNSS: TrackSideRecall(staged_aircraft=100, detected_aircraft=82)},
    )
    arm = metrics.for_arm(GNSS)

    assert arm.recall_per_run == 1.0
    assert arm.track_side is not None
    assert arm.track_side.recall_per_staged_aircraft == pytest.approx(0.82)
    exported = arm.as_json()
    assert exported["recall_per_run"] == 1.0
    assert exported["track_side"]["recall_per_staged_aircraft"] == pytest.approx(0.82)


def test_an_arm_with_no_track_side_measurement_carries_none_not_a_zero() -> None:
    # spec: eval-002
    # A per-aircraft recall of 0.0 on an arm nobody measured reads as a
    # detector that saw nothing, which is eval-005's rule one item along.
    assert _computed().for_arm(SENSOR_FAULT).track_side is None


def test_a_track_side_recall_for_an_arm_outside_the_population_is_refused() -> None:
    # spec: eval-002
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.scenario_type != AMBIGUOUS]
    with pytest.raises(MetricsError, match="was not scored"):
        compute(
            outcomes,
            controls=controls,
            track_side={AMBIGUOUS: TrackSideRecall(10, 5)},
        )


def test_a_track_side_recall_for_an_arm_that_stages_nothing_is_refused() -> None:
    # spec: eval-002, anom-011
    # anom-011 refuses a run that staged nothing rather than scoring it nought
    # or a hundred, so the quiet arm has no per-aircraft recall to carry --
    # unlike aircraft-coverage-gap, which is one of the arms it measures.
    outcomes, controls = _corpus()
    with pytest.raises(MetricsError, match="stages nothing"):
        compute(
            outcomes,
            controls=controls,
            track_side={BASELINE: TrackSideRecall(10, 5)},
        )


def test_the_unjudged_arm_still_carries_a_track_side_recall() -> None:
    # spec: eval-002, anom-011
    # It is unjudged by the *reportable* rules and is one of anom-011's two
    # suppression arms, so its per-aircraft figure exists where its run-level
    # one does not -- the clearest case for keeping the two apart.
    outcomes, controls = _corpus()
    metrics = compute(
        outcomes,
        controls=controls,
        track_side={COVERAGE_GAP: TrackSideRecall(100, 59)},
    )
    arm = metrics.for_arm(COVERAGE_GAP)
    assert arm.recall_per_run is None
    assert arm.track_side is not None
    assert arm.track_side.recall_per_staged_aircraft == pytest.approx(0.59)


def test_a_track_side_recall_detecting_more_than_was_staged_is_refused() -> None:
    # spec: eval-002
    with pytest.raises(MetricsError, match="more aircraft"):
        TrackSideRecall(staged_aircraft=10, detected_aircraft=11)


def test_a_track_side_recall_over_no_staged_aircraft_is_none() -> None:
    # spec: eval-002
    assert TrackSideRecall(0, 0).recall_per_staged_aircraft is None


def test_a_track_side_recall_counting_a_negative_number_is_refused() -> None:
    # spec: eval-002
    # A count below zero makes the rate readable and wrong, which is worse
    # than an error: nothing downstream can tell it from a measurement.
    with pytest.raises(MetricsError, match="negative"):
        TrackSideRecall(staged_aircraft=-1, detected_aircraft=0)
    with pytest.raises(MetricsError, match="negative"):
        TrackSideRecall(staged_aircraft=10, detected_aircraft=-1)


# --- recall by truth, precision by prediction ------------------------------


def test_a_misreported_run_is_a_miss_for_one_arm_and_an_alarm_for_one_type() -> None:
    # spec: eval-002, anom-013
    # The whole reason this is one multi-class confusion: three independent
    # binary tests would count this run once and lose half of it.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "g1"]
    outcomes.append(RunOutcome(run_id="g1", scenario_type=GNSS, reported=(FAULT,)))
    metrics = compute(outcomes, controls=controls)

    arm = metrics.for_arm(GNSS)
    assert (arm.detected, arm.missed) == (1, 1)
    assert arm.recall_per_run == 0.5

    claimed = metrics.for_type(FAULT)
    assert (claimed.correct, claimed.wrong) == (4, 1)
    assert claimed.precision == pytest.approx(4 / 5)

    # And the two figures sit under different denominators.
    assert arm.runs == 2
    assert claimed.claimed_runs == 5


def test_recall_and_precision_are_not_the_same_number_on_the_same_label() -> None:
    # spec: eval-002
    # The arm and the type carry the same name in prose and different
    # denominators in fact, which is why they are separate rows.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "c1"]
    outcomes.append(
        RunOutcome(run_id="c1", scenario_type=COVERAGE_GAP, reported=(INTERFERENCE,))
    )
    metrics = compute(outcomes, controls=controls)

    assert metrics.for_arm(GNSS).recall_per_run == 1.0
    assert metrics.for_type(INTERFERENCE).precision == pytest.approx(2 / 3)


def test_the_confusion_matrix_places_a_misreport_off_the_diagonal() -> None:
    # spec: eval-002
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "g1"]
    outcomes.append(RunOutcome(run_id="g1", scenario_type=GNSS, reported=(FAULT,)))
    metrics = compute(outcomes, controls=controls)

    assert metrics.confusion[GNSS][FAULT] == 1
    assert metrics.confusion[GNSS][INTERFERENCE] == 1
    assert metrics.confusion[BASELINE][SILENT] == 2


def test_a_run_reporting_two_types_is_counted_once_per_type_and_flagged() -> None:
    # spec: eval-002
    # anom-013 suppresses within a zone and a run may hold several zones, so
    # the row sums can exceed the run count. Counted rather than assumed away.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "g1"]
    outcomes.append(
        RunOutcome(run_id="g1", scenario_type=GNSS, reported=(INTERFERENCE, FAULT))
    )
    metrics = compute(outcomes, controls=controls)

    assert metrics.multi_claim_runs == 1
    assert metrics.for_arm(GNSS).detected == 2
    assert metrics.for_type(FAULT).wrong == 1
    # Both claims reach the matrix. Keeping only the first would make the
    # row sum to the run count and look correct.
    assert metrics.confusion[GNSS] == {INTERFERENCE: 2, FAULT: 1}


def test_the_false_negative_rate_is_the_complement_of_the_run_level_recall() -> None:
    # spec: eval-002
    # Three runs rather than two, so the two figures differ: at a recall of
    # one half they are the same number and the assertion proves nothing.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "f1"]
    outcomes += [
        RunOutcome(run_id="f1", scenario_type=SENSOR_FAULT),
        RunOutcome(run_id="f3", scenario_type=SENSOR_FAULT, reported=(FAULT,)),
    ]
    arm = compute(outcomes, controls=controls).for_arm(SENSOR_FAULT)
    assert arm.recall_per_run == pytest.approx(2 / 3)
    assert arm.false_negative_rate == pytest.approx(1 / 3)


# --- F1 only where one arm maps to one type --------------------------------


def test_f1_is_emitted_where_one_arm_maps_to_one_type() -> None:
    # spec: eval-002
    interference = _computed().for_type(INTERFERENCE)
    assert interference.arms == (GNSS,)
    assert interference.f1_is_defined
    assert interference.f1 == pytest.approx(1.0)


def test_f1_is_withheld_where_two_arms_map_to_one_type_and_the_row_says_so() -> None:
    # spec: eval-002, anom-006
    # rf-sensor-fault and ambiguous-mixed-evidence are both decided
    # possible_sensor_fault, so there is no arm this type's F1 would be about.
    # The reason is readable off the data rather than carried as prose.
    fault = _computed().for_type(FAULT)
    assert fault.arms == (AMBIGUOUS, SENSOR_FAULT)
    assert not fault.f1_is_defined
    assert fault.f1 is None
    assert fault.precision == 1.0


def test_f1_is_withheld_where_precision_or_recall_is_unmeasured() -> None:
    # spec: eval-002
    # possible_data_source_issue is never claimed and never staged by a built
    # rule, so both halves are None and their harmonic mean is not 0.0.
    source = _computed().for_type(SOURCE_GAP)
    assert source.claimed_runs == 0
    assert source.precision is None
    assert source.arm_recall_per_run is None
    assert source.f1 is None
    assert not source.f1_is_defined


def test_the_arms_behind_a_type_are_the_ones_a_built_rule_judges() -> None:
    # spec: eval-002, anom-006
    # aircraft-coverage-gap stages what anom-006 would claim, and listing it
    # here would make possible_data_source_issue look like a tested arm whose
    # recall happens to be missing rather than one with no rule at all.
    assert _computed().for_type(SOURCE_GAP).arms == ()


def test_f1_over_a_precision_and_a_recall_of_zero_is_absent_not_zero() -> None:
    # spec: eval-002
    # Their harmonic mean is a division by zero, which is this item's named
    # failure case arriving where nobody looks for it.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.scenario_type not in {GNSS, COVERAGE_GAP}]
    outcomes += [
        RunOutcome(run_id="g1", scenario_type=GNSS),
        RunOutcome(run_id="g2", scenario_type=GNSS),
        RunOutcome(run_id="c1", scenario_type=COVERAGE_GAP, reported=(INTERFERENCE,)),
        RunOutcome(run_id="c2", scenario_type=COVERAGE_GAP),
    ]
    row = compute(outcomes, controls=controls).for_type(INTERFERENCE)
    assert row.precision == 0.0
    assert row.arm_recall_per_run == 0.0
    assert row.f1 is None


def test_a_single_arm_recall_on_a_type_two_arms_produce_is_refused() -> None:
    # spec: eval-002
    # Held at construction rather than checked again where F1 is read: two
    # checks over one rule can each be removed with the behaviour unchanged,
    # which is a rule no test is proving.
    with pytest.raises(MetricsError, match="arms produce it"):
        TypePrecision(
            anomaly_type=FAULT,
            built=True,
            arms=(AMBIGUOUS, SENSOR_FAULT),
            claimed_runs=4,
            correct=4,
            wrong=0,
            arm_recall_per_run=1.0,
        )


# --- two false-positive rates ----------------------------------------------


def test_the_two_false_positive_rates_are_reported_separately() -> None:
    # spec: eval-002
    # A report from nothing and a report leaking across modalities are
    # different failures, and one pooled figure cannot say which happened.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "c1"]
    # Two claims on one run, so a rate counting claims rather than runs comes
    # out at one rather than a half.
    outcomes.append(
        RunOutcome(
            run_id="c1", scenario_type=COVERAGE_GAP, reported=(INTERFERENCE, FAULT)
        )
    )
    metrics = compute(outcomes, controls=controls)

    from_nothing = metrics.for_negative(NegativeArm.FROM_NOTHING)
    cross_modal = metrics.for_negative(NegativeArm.CROSS_MODAL)

    assert from_nothing.scenario_type == BASELINE
    assert from_nothing.rate == 0.0
    assert cross_modal.scenario_type == COVERAGE_GAP
    assert cross_modal.rate == 0.5
    assert {rate.arm for rate in metrics.false_positive_rates} == set(NegativeArm)


def test_nothing_exported_pools_the_two_negative_arms() -> None:
    # spec: eval-002
    exported = _computed().as_json()
    assert "false_positive_rate" not in exported
    assert len(exported["false_positive_rates"]) == 2


def test_only_the_from_nothing_rate_is_backed_by_a_control() -> None:
    # spec: eval-002, anom-008
    # anom-008 grades quiet runs only. A coverage-gap run stages something, so
    # its silence is a measurement rather than a control, and the rate says so
    # rather than borrowing the assurance of the arm beside it.
    metrics = _computed()
    assert metrics.for_negative(NegativeArm.FROM_NOTHING).controlled
    assert not metrics.for_negative(NegativeArm.CROSS_MODAL).controlled


def test_every_false_positive_rate_carries_the_control_coverage() -> None:
    # spec: eval-002, anom-006, anom-008
    # Read as three reportable types, either rate overstates the layer's
    # coverage by exactly the rule that does not exist.
    for rate in _computed().false_positive_rates:
        assert rate.coverage == "2 of 3"
        assert rate.as_json()["reportable_types"] == "2 of 3"


# --- the control guard -----------------------------------------------------


def test_a_false_positive_rate_is_refused_when_the_control_does_not_hold() -> None:
    # spec: eval-002, anom-008
    outcomes, controls = _corpus()
    controls["b2"] = _leaking("b2")
    with pytest.raises(MetricsError, match="did not pass"):
        compute(outcomes, controls=controls)


def test_a_quiet_run_with_no_control_is_refused() -> None:
    # spec: eval-002, anom-008
    # Zero is the answer the control wants and also the answer a pipeline
    # that never ran gives, so an ungraded quiet run cannot contribute.
    outcomes, controls = _corpus()
    del controls["b2"]
    with pytest.raises(MetricsError, match="no anom-008 control"):
        compute(outcomes, controls=controls)


def test_a_control_for_a_run_outside_the_population_is_refused() -> None:
    # spec: eval-002
    # Two halves of one report describing different populations, with
    # nothing saying so -- eval-005's refusal one item along.
    outcomes, controls = _corpus()
    controls["b9"] = _clean("b9")
    with pytest.raises(MetricsError, match="not in the population"):
        compute(outcomes, controls=controls)


def test_a_control_filed_under_another_run_id_is_refused() -> None:
    # spec: eval-002
    outcomes, controls = _corpus()
    controls["b2"] = _clean("b1")
    with pytest.raises(MetricsError, match="filed under"):
        compute(outcomes, controls=controls)


# --- latency conditional on detection --------------------------------------


def test_latency_is_reported_over_the_detections_and_labels_itself_so() -> None:
    # spec: eval-002, anom-009
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "g1"]
    outcomes.append(RunOutcome(run_id="g1", scenario_type=GNSS))
    latency = compute(outcomes, controls=controls).for_arm(GNSS).latency

    assert latency.detections == 1
    assert latency.measured == 1
    assert latency.median_seconds == 60.0
    assert latency.as_json()["conditional_on"] == "detections"


def test_a_detection_carrying_no_latency_is_visible_rather_than_silent() -> None:
    # spec: eval-002
    # Otherwise the median quietly moves to whichever detections happened to
    # be instrumented, with nothing in the report saying how many.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "g1"]
    outcomes.append(
        RunOutcome(run_id="g1", scenario_type=GNSS, reported=(INTERFERENCE,))
    )
    latency = compute(outcomes, controls=controls).for_arm(GNSS).latency
    assert (latency.detections, latency.measured) == (2, 1)


def test_an_arm_with_no_detections_has_no_latency_rather_than_zero() -> None:
    # spec: eval-002
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.scenario_type != GNSS]
    outcomes += [
        RunOutcome(run_id="g1", scenario_type=GNSS),
        RunOutcome(run_id="g2", scenario_type=GNSS),
    ]
    latency = compute(outcomes, controls=controls).for_arm(GNSS).latency
    assert latency.detections == 0
    assert latency.median_seconds is None
    assert latency.min_seconds is None


def test_a_negative_latency_is_carried_rather_than_clamped() -> None:
    # spec: eval-002, anom-009
    # anom-009 keeps the sign because it says the rule swept in readings from
    # before the incident; clamping here would read as instant detection.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.run_id != "g1"]
    outcomes.append(
        RunOutcome(
            run_id="g1",
            scenario_type=GNSS,
            reported=(INTERFERENCE,),
            latency_seconds=-10.0,
        )
    )
    latency = compute(outcomes, controls=controls).for_arm(GNSS).latency
    assert latency.min_seconds == -10.0
    assert latency.median_seconds == pytest.approx(25.0)


def test_a_latency_on_a_run_that_reported_nothing_is_refused() -> None:
    # spec: eval-002
    with pytest.raises(MetricsError, match="conditional on detection"):
        RunOutcome(run_id="g1", scenario_type=GNSS, latency_seconds=40.0)


def test_a_latency_on_a_run_that_reported_the_wrong_type_is_refused() -> None:
    # spec: eval-002
    with pytest.raises(MetricsError, match="conditional on detection"):
        RunOutcome(
            run_id="g1",
            scenario_type=GNSS,
            reported=(FAULT,),
            latency_seconds=40.0,
        )


def test_a_latency_on_a_silent_arm_is_refused() -> None:
    # spec: eval-002
    with pytest.raises(MetricsError, match="conditional on detection"):
        RunOutcome(
            run_id="b1", scenario_type=BASELINE, staged=False, latency_seconds=1.0
        )


# --- exclusions and refusals -----------------------------------------------


def test_a_staged_type_run_that_staged_nothing_is_excluded_and_counted() -> None:
    # spec: eval-002, scn-006, anom-011
    # A baseline run wearing the wrong label. Scored, a rule correctly
    # reporting nothing on it is counted as having missed something.
    outcomes, controls = _corpus()
    outcomes.append(RunOutcome(run_id="g3", scenario_type=GNSS, staged=False))
    metrics = compute(outcomes, controls=controls)

    arm = metrics.for_arm(GNSS)
    assert arm.runs == 2
    assert arm.excluded == 1
    assert arm.recall_per_run == 1.0
    assert metrics.excluded == 1
    assert metrics.runs == 10


def test_an_excluded_run_reaches_no_rate_at_all() -> None:
    # spec: eval-002
    # The amendment's point: excluding it from recall alone still lets it
    # into precision and the false-positive rate.
    outcomes, controls = _corpus()
    outcomes.append(
        RunOutcome(
            run_id="g3", scenario_type=GNSS, staged=False, reported=(INTERFERENCE,)
        )
    )
    metrics = compute(outcomes, controls=controls)
    assert metrics.for_type(INTERFERENCE).claimed_runs == 2
    assert metrics.confusion[GNSS][INTERFERENCE] == 2


def test_a_normal_baseline_run_that_claims_to_have_staged_something_is_refused() -> (
    None
):
    # spec: eval-002
    with pytest.raises(MetricsError, match="stages nothing"):
        RunOutcome(run_id="b1", scenario_type=BASELINE, staged=True)


def test_an_unrecognised_scenario_type_is_refused() -> None:
    # spec: eval-002, scn-002
    # Five and only five. A sixth means the ground-truth table is out of date
    # rather than that one run is odd -- eval-004's rule for an unknown kind.
    with pytest.raises(MetricsError, match="not one of the five"):
        RunOutcome(run_id="x1", scenario_type="jamming-suspected")


def test_an_intermediate_finding_type_in_the_report_is_refused() -> None:
    # spec: eval-002, anom-008
    # A quiet run genuinely holds ~138 track discontinuities. Counted as
    # reportable output they would be a false-positive rate of one.
    outcomes, controls = _corpus()
    outcomes.append(
        RunOutcome(run_id="g3", scenario_type=GNSS, reported=("track_continuity_gap",))
    )
    with pytest.raises(MetricsError, match="not a reportable"):
        compute(outcomes, controls=controls)


def test_a_repeated_anomaly_type_on_one_run_is_refused() -> None:
    # spec: eval-002
    with pytest.raises(MetricsError, match="twice"):
        RunOutcome(
            run_id="g1", scenario_type=GNSS, reported=(INTERFERENCE, INTERFERENCE)
        )


def test_a_repeated_run_id_is_refused() -> None:
    # spec: eval-002
    outcomes, controls = _corpus()
    outcomes.append(RunOutcome(run_id="g1", scenario_type=GNSS))
    with pytest.raises(MetricsError, match="twice"):
        compute(outcomes, controls=controls)


def test_an_empty_population_is_refused() -> None:
    # spec: eval-002
    with pytest.raises(MetricsError, match="no runs"):
        compute([], controls={})


# --- the arms, and what makes one unjudged ---------------------------------


def test_the_silent_control_and_the_unjudged_arm_are_different_kinds() -> None:
    # spec: eval-002
    metrics = _computed()
    assert metrics.for_arm(BASELINE).kind is ArmKind.SILENT_CONTROL
    assert metrics.for_arm(COVERAGE_GAP).kind is ArmKind.UNJUDGED
    assert metrics.for_arm(GNSS).kind is ArmKind.POSITIVE


def test_the_unjudged_arm_contributes_no_true_positives() -> None:
    # spec: eval-002
    # Its correct non-detections are correct only because no built rule
    # judges it, so it must never be counted as a tested positive.
    arm = _computed().for_arm(COVERAGE_GAP)
    assert arm.runs == 2
    assert arm.detected == 0
    assert arm.recall_per_run is None
    assert arm.false_negative_rate is None


def test_the_unjudged_arm_becomes_positive_when_its_rule_is_built() -> None:
    # spec: eval-002, anom-006
    # What makes that arm unjudged is a property of the register, not a
    # decision written into this module: build anom-006 and the arm is a
    # positive one with no edit here at all.
    register = build_register(
        *(
            (
                Producer(
                    rule_id=p.rule_id,
                    finding_type=p.finding_type,
                    kind=p.kind,
                    background=p.background,
                    built=True,
                    note=p.note,
                )
                if p.rule_id == SOURCE_GAP_RULE
                else p
            )
            for p in REGISTER.values()
        )
    )
    outcomes, _ = _corpus()
    outcomes = [o for o in outcomes if o.scenario_type != COVERAGE_GAP]
    outcomes += [
        RunOutcome(run_id="c1", scenario_type=COVERAGE_GAP, reported=(SOURCE_GAP,)),
        RunOutcome(run_id="c2", scenario_type=COVERAGE_GAP),
    ]
    controls = {"b1": _clean("b1", register), "b2": _clean("b2", register)}
    metrics = compute(outcomes, controls=controls, register=register)

    arm = metrics.for_arm(COVERAGE_GAP)
    assert arm.kind is ArmKind.POSITIVE
    assert arm.recall_per_run == 0.5
    assert metrics.for_type(SOURCE_GAP).arms == (COVERAGE_GAP,)
    assert [rate.arm for rate in metrics.false_positive_rates] == [
        NegativeArm.FROM_NOTHING
    ]
    assert metrics.for_negative(NegativeArm.FROM_NOTHING).coverage == "3 of 3"
    # And the rate that no longer exists is absent rather than zero: an arm
    # with a rule to judge it is no longer a test of silence.
    with pytest.raises(KeyError):
        metrics.for_negative(NegativeArm.CROSS_MODAL)


def test_every_scenario_type_gets_a_row_whether_or_not_it_was_run() -> None:
    # spec: eval-002
    # A table missing the arm nobody generated reads as a table of five.
    outcomes, controls = _corpus()
    outcomes = [o for o in outcomes if o.scenario_type != AMBIGUOUS]
    metrics = compute(outcomes, controls=controls)
    arm = metrics.for_arm(AMBIGUOUS)
    assert arm.runs == 0
    assert arm.recall_per_run is None
    assert {a.scenario_type for a in metrics.arms} == {
        BASELINE,
        GNSS,
        SENSOR_FAULT,
        COVERAGE_GAP,
        AMBIGUOUS,
    }


def test_every_registered_reportable_type_gets_a_row() -> None:
    # spec: eval-002, anom-008
    # Taken from the control's register rather than listed here, so the
    # coverage figure and the table cannot disagree.
    metrics = _computed()
    assert [t.anomaly_type for t in metrics.types] == sorted(
        [FAULT, INTERFERENCE, SOURCE_GAP]
    )
    assert metrics.for_type(SOURCE_GAP).built is False


def test_an_unknown_arm_or_type_is_a_key_error_rather_than_a_default() -> None:
    # spec: eval-002
    metrics = _computed()
    with pytest.raises(KeyError):
        metrics.for_arm("jamming-suspected")
    with pytest.raises(KeyError):
        metrics.for_type("possible_jamming")


def test_the_whole_report_serialises() -> None:
    # spec: eval-002, eval-003
    # eval-003 exports this; a report carrying anything json cannot render
    # would fail there rather than here.
    exported = json.loads(json.dumps(_computed().as_json()))
    assert exported["runs"] == 10
    assert exported["excluded"] == 0
    assert len(exported["arms"]) == 5
    assert len(exported["types"]) == 3
