"""Correct non-detection on a quiet run. Spec: anom-008.

**The control has to be unsatisfiable by silence, and that is the whole
difficulty.** An empty list of reportable anomalies is what a correct quiet
run produces. It is also what a run produces when the detectors never ran,
when they were handed the wrong observations, or when a filter upstream
discarded everything -- and on the reportable side, where zero is the
required answer, no amount of counting can tell those apart. So the control
is given an **account of every registered producer** and refuses to grade a
run where one is missing, rather than grading whatever it was handed.

Two asymmetries from the rules themselves shape the rest. The lower
producers read **replayed** track data, which genuinely contains gaps, so
their silence is a failure; the RF grid is **synthetic** and a quiet run has
nothing injected into it, so its silence is correct -- `anom-014` measured
`anom-001` raising anything at all on 14 of 100 unstaged runs. Neither is a
special case here: the measured band carries both, its floor being above
zero on one side and zero on the other.

And `anom-006` has no rule at all. Reporting zero `possible_data_source_issue`
across forty quiet runs would be quoting the absence of a rule as the
accuracy of one, so the register carries it and the verdict says
*not exercised*.
"""

from __future__ import annotations

import pytest

from app.detection.control import (
    REGISTER,
    Background,
    Control,
    ControlError,
    Kind,
    Outcome,
    Producer,
    audit,
)
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE
from app.detection.fusion import RULE_ID as FUSION
from app.detection.precedence import RULE_ORDER
from app.detection.rf_noise import ANOMALY_TYPE as RF_DEVIATION
from app.detection.rf_noise import RULE_ID as RF_NOISE
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT_TYPE
from app.detection.sensor_fault import RULE_ID as SENSOR_FAULT
from app.detection.track_gap import FINDING_TYPE as CONTINUITY_GAP
from app.detection.track_gap import RULE_ID as TRACK_GAP

QUIET = "normal-baseline"
RUN = "run-quiet-01"

#: A register of its own, so the assertions below do not move when the real
#: bands are re-measured. The real one is checked for shape, not for values.
NOISY = Producer(
    rule_id=TRACK_GAP,
    finding_type=CONTINUITY_GAP,
    kind=Kind.INTERMEDIATE,
    background=Background(low=2, high=9, runs=40),
)
SILENT_BY_DESIGN = Producer(
    rule_id=RF_NOISE,
    finding_type=RF_DEVIATION,
    kind=Kind.INTERMEDIATE,
    background=Background(low=0, high=2, runs=40),
)
SHOWN = Producer(
    rule_id=SENSOR_FAULT, finding_type=FAULT_TYPE, kind=Kind.REPORTABLE
)
UNBUILT = Producer(
    rule_id="SOURCE-GAP",
    finding_type="possible_data_source_issue",
    kind=Kind.REPORTABLE,
    built=False,
)

BENCH = {p.key: p for p in (NOISY, SILENT_BY_DESIGN, SHOWN, UNBUILT)}
FULL_ACCOUNT = {NOISY.key: 5, SILENT_BY_DESIGN.key: 0, SHOWN.key: 0}


def graded(counts, *, register=BENCH, scenario_type=QUIET) -> Control:
    return audit(
        run_id=RUN, scenario_type=scenario_type, counts=counts, register=register
    )


def outcome_for(control: Control, producer: Producer) -> Outcome:
    return next(v.outcome for v in control.verdicts if v.producer.key == producer.key)


# --- the account, which is what makes silence insufficient ----------------


def test_an_empty_account_is_refused_rather_than_passing() -> None:
    # spec: anom-008 -- the headline. Zero reportable anomalies is the
    # required answer, so a control that grades an empty input would report
    # a perfect quiet run for a pipeline that never ran.
    with pytest.raises(ControlError, match="accounted for"):
        graded({})


def test_a_registered_producer_missing_from_the_account_is_refused() -> None:
    # spec: anom-008
    account = dict(FULL_ACCOUNT)
    del account[NOISY.key]
    with pytest.raises(ControlError, match=CONTINUITY_GAP):
        graded(account)


def test_a_producer_outside_the_register_is_refused() -> None:
    # spec: anom-008 -- an unregistered producer means a detector landed
    # that this control has never been asked about, following anom-013's
    # refusal of a claim whose rule has no declared position.
    with pytest.raises(ControlError, match="NEW-RULE"):
        graded({**FULL_ACCOUNT, ("NEW-RULE", "something"): 3})


def test_a_count_supplied_for_a_rule_that_does_not_exist_is_refused() -> None:
    # spec: anom-008 -- counted output from an unimplemented rule is a
    # caller error, not a run property.
    with pytest.raises(ControlError, match="no implementation"):
        graded({**FULL_ACCOUNT, UNBUILT.key: 0})


def test_a_negative_count_is_refused() -> None:
    # spec: anom-008
    with pytest.raises(ControlError, match="negative"):
        graded({**FULL_ACCOUNT, SHOWN.key: -1})


def test_a_staged_scenario_type_is_not_a_quiet_run() -> None:
    # spec: anom-008 -- a run of a staged type that staged nothing is
    # eval-002's exclusion, counted and reported there. Folding it in here
    # would put a run the generator failed on into a figure about the
    # detectors.
    with pytest.raises(ControlError, match="normal-baseline"):
        graded(FULL_ACCOUNT, scenario_type="rf-sensor-fault")


# --- the reportable side --------------------------------------------------


def test_a_quiet_run_showing_the_analyst_nothing_holds() -> None:
    # spec: anom-008
    control = graded(FULL_ACCOUNT)
    assert control.holds
    assert outcome_for(control, SHOWN) is Outcome.CLEAN


def test_one_reportable_claim_is_a_false_positive() -> None:
    # spec: anom-008 -- the failure case the item was written for.
    control = graded({**FULL_ACCOUNT, SHOWN.key: 1})
    assert not control.holds
    assert outcome_for(control, SHOWN) is Outcome.FALSE_POSITIVE
    assert [v.producer.key for v in control.false_positives] == [SHOWN.key]


# --- the measured band, which carries "zero fails" ------------------------


def test_a_count_inside_the_band_is_within_background() -> None:
    # spec: anom-008
    control = graded({**FULL_ACCOUNT, NOISY.key: 5})
    assert outcome_for(control, NOISY) is Outcome.WITHIN_BACKGROUND


def test_a_track_producer_reporting_nothing_is_outside_its_background() -> None:
    # spec: anom-008 -- the corpus is known to contain continuity gaps, so
    # silence here means the detector did not look.
    control = graded({**FULL_ACCOUNT, NOISY.key: 0})
    assert not control.holds
    assert outcome_for(control, NOISY) is Outcome.OUTSIDE_BACKGROUND


def test_an_rf_producer_reporting_nothing_is_within_its_background() -> None:
    # spec: anom-008 -- and this is not an exception carved for the RF
    # rule. The grid is synthetic and a quiet run has nothing injected into
    # it, so its measured floor is zero and the same comparison passes.
    control = graded({**FULL_ACCOUNT, SILENT_BY_DESIGN.key: 0})
    assert control.holds
    assert outcome_for(control, SILENT_BY_DESIGN) is Outcome.WITHIN_BACKGROUND


def test_a_count_above_the_band_is_outside_it() -> None:
    # spec: anom-008 -- drift in the corpus or the generator, which is the
    # one thing this number exists to notice.
    control = graded({**FULL_ACCOUNT, NOISY.key: 10})
    assert not control.holds
    assert outcome_for(control, NOISY) is Outcome.OUTSIDE_BACKGROUND


def test_both_ends_of_the_band_belong_to_it() -> None:
    # spec: anom-008 -- anom-014's rule that a boundary belongs to the
    # configured value and not to the comparison.
    low = graded({**FULL_ACCOUNT, NOISY.key: 2})
    high = graded({**FULL_ACCOUNT, NOISY.key: 9})
    assert outcome_for(low, NOISY) is Outcome.WITHIN_BACKGROUND
    assert outcome_for(high, NOISY) is Outcome.WITHIN_BACKGROUND


# --- the rule that does not exist -----------------------------------------


def test_the_unbuilt_rule_is_not_exercised_and_never_clean() -> None:
    # spec: anom-008
    control = graded(FULL_ACCOUNT)
    assert outcome_for(control, UNBUILT) is Outcome.NOT_EXERCISED
    assert control.holds


def test_a_holding_control_still_reports_how_many_types_it_covers() -> None:
    # spec: anom-008 -- read as three reportable types, the false-positive
    # rate overstates the layer's coverage by exactly the rule that does
    # not exist, so eval-002 has to be able to quote the pair.
    control = graded(FULL_ACCOUNT)
    assert control.reportable_types_covered == 1
    assert control.reportable_types_registered == 2
    assert control.as_json()["reportable_types"] == "1 of 2"


# --- the register itself --------------------------------------------------


def test_every_rule_in_the_ladder_is_registered() -> None:
    # spec: anom-008 -- a fourth reportable rule landing in anom-013's
    # order and not here would escape the control entirely, and nothing
    # else in the repo would say so.
    registered = {p.rule_id for p in REGISTER.values() if p.kind is Kind.REPORTABLE}
    assert registered == set(RULE_ORDER)


def test_the_register_is_keyed_on_the_pair_and_not_the_rule_id() -> None:
    # spec: anom-008 -- anom-012 borrows anom-010's rule id, so a rate
    # excess and a continuity gap are one key by rule id while making
    # different claims. Keyed on the rule alone, one of them would silently
    # replace the other.
    under_track_gap = [k for k in REGISTER if k[0] == TRACK_GAP]
    assert len(under_track_gap) > 1
    assert len({k[1] for k in under_track_gap}) == len(under_track_gap)


def test_every_intermediate_producer_carries_a_measured_background() -> None:
    # spec: anom-008 -- the band is what makes "zero fails" a measurement
    # rather than an assertion, so an intermediate without one is refused
    # at construction.
    for producer in REGISTER.values():
        if producer.kind is Kind.INTERMEDIATE:
            assert producer.background is not None
            assert producer.background.runs > 0


def test_no_reportable_producer_carries_a_background() -> None:
    # spec: anom-008 -- zero is this side's requirement and not a figure
    # measured off the corpus. A band here would make a false positive
    # negotiable.
    for producer in REGISTER.values():
        if producer.kind is Kind.REPORTABLE:
            assert producer.background is None


def test_the_unbuilt_rule_is_registered_rather_than_absent() -> None:
    # spec: anom-008
    unbuilt = [p for p in REGISTER.values() if not p.built]
    assert [p.rule_id for p in unbuilt] == ["SOURCE-GAP"]


def test_the_two_built_reportable_rules_are_the_ones_with_modules() -> None:
    # spec: anom-008
    built = {p.rule_id for p in REGISTER.values() if p.kind is Kind.REPORTABLE and p.built}
    assert built == {SENSOR_FAULT, FUSION}
    assert {p.finding_type for p in REGISTER.values() if p.rule_id == FUSION} == {
        INTERFERENCE
    }


# --- construction ---------------------------------------------------------


def test_a_band_whose_top_is_below_its_floor_is_refused() -> None:
    # spec: anom-008
    with pytest.raises(ControlError, match="below"):
        Background(low=4, high=1, runs=40)


def test_a_band_measured_over_no_runs_is_refused() -> None:
    # spec: anom-008 -- a band without its n is a memory, not a
    # measurement, and this project has already been caught quoting one.
    with pytest.raises(ControlError, match="runs"):
        Background(low=0, high=2, runs=0)


def test_an_intermediate_producer_without_a_band_is_refused() -> None:
    # spec: anom-008
    with pytest.raises(ControlError, match="background"):
        Producer(rule_id="X", finding_type="y", kind=Kind.INTERMEDIATE)


def test_a_reportable_producer_given_a_band_is_refused() -> None:
    # spec: anom-008
    with pytest.raises(ControlError, match="background"):
        Producer(
            rule_id="X",
            finding_type="y",
            kind=Kind.REPORTABLE,
            background=Background(low=0, high=1, runs=40),
        )
