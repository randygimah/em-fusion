"""Correct non-detection on a quiet run. Spec: anom-008.

Every figure about how *good* the detection is rests on a figure about how
*quiet* it is: a catch rate can be driven to one by alarming on everything,
so it says nothing until the layer can be shown to stay silent on ordinary
data. This is the instrument that shows it, and `eval-002` takes its
false-positive rate from here.

**The difficulty is that the control must be unsatisfiable by silence.** An
empty list of reportable anomalies is what a correct quiet run produces. It
is also what a run produces when the detectors never ran, when they were
handed the wrong observations, or when a filter upstream discarded
everything -- and on the reportable side, where zero is the required answer,
no amount of counting can separate those. So a run is graded against an
**account of every registered producer**, and a producer missing from that
account is refused rather than skipped. That refusal, and not a count, is
what answers *did this detector actually look*.

Three consequences of reading the rules this grades.

**The register is keyed on the `(rule_id, finding_type)` pair** `ai-001`
defines, which is `ai-008`'s resolution key and `eval-007`'s grouping.
`anom-012` borrows `anom-010`'s rule id, so keyed on the rule alone a rate
excess and a continuity gap are one row and one would silently replace the
other. An unregistered producer is refused, following `anom-013`'s rule that
a claim whose rule has no declared position is refused rather than appended.

**"Zero fails" is carried by the measured band and is not asserted.** The
item's amendment of 2026-09-14 justified the non-zero requirement entirely
from replayed track data, which genuinely contains gaps -- and it does not
hold on the RF side, where the grid is synthetic and a quiet run has nothing
injected into it. Measured over corpus v2's quiet runs, `anom-001` raises
**nothing at all on 20 of 20**, so a blanket non-zero rule would have failed
every one of them for being right. The floor is therefore measured per
producer: above zero on the track side, so its silence fails; zero on the RF
side, so its silence passes. Neither is a special case, and the difference
is a property of the data rather than of this module.

**A rule that does not exist is not a rule that found nothing.** `anom-006`
has no implementation: it was attempted twice, measured, and closed on the
corpus as generated. Reporting zero `possible_data_source_issue` across
twenty quiet runs would be quoting the absence of a rule as the accuracy of
one, so it is registered, reported as *not exercised*, and the control
carries how many reportable types it actually covers -- two of three -- for
`eval-002` to quote alongside the rate. This module is the only place in
`app/` that names that rule's vocabulary, which is itself the record that it
is missing rather than forgotten.

The bands are measured in `measurements/corpus/quiet_run_background.py` and
its committed log. They are measured on this corpus's quiet runs and applied
to them, so **they cannot fail on the data that produced them**: they are a
drift tripwire for a later corpus or a changed generator, which is the
purpose `anom-008` states for them, and not an independent test of the
present figures. A band is the observed minimum and maximum, so a fresh run
from the same distribution falls outside it at roughly 2/(n+1) -- about one
in ten at n=20. The per-run verdict is therefore an input, and the figure
worth quoting is the proportion of quiet runs in band.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.detection.clustering import FINDING_TYPE as CLUSTER_TYPE
from app.detection.clustering import RULE_ID as CLUSTER_RULE
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE_TYPE
from app.detection.fusion import RULE_ID as FUSION_RULE
from app.detection.rate_excess import FINDING_TYPE as EXCESS_TYPE
from app.detection.rf_noise import ANOMALY_TYPE as RF_TYPE
from app.detection.rf_noise import RULE_ID as RF_RULE
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT_TYPE
from app.detection.sensor_fault import RULE_ID as FAULT_RULE
from app.detection.track_gap import FINDING_TYPE as GAP_TYPE
from app.detection.track_gap import RULE_ID as GAP_RULE

#: `anom-006`'s vocabulary, which no module defines because no module
#: implements it. Named here so the register can carry the rule as absent
#: rather than leave it indistinguishable from a rule that found nothing.
SOURCE_GAP_RULE = "SOURCE-GAP"
SOURCE_GAP_TYPE = "possible_data_source_issue"

#: The one scenario type this control grades. A run of a staged type that
#: staged nothing is `eval-002`'s exclusion, counted and reported there:
#: folding it in here would put a run the *generator* failed on into a
#: figure about the detectors.
QUIET = "normal-baseline"

Key = tuple[str, str]


class ControlError(ValueError):
    """A run this control refuses to grade, or a register it refuses to hold."""


class Kind(str, Enum):
    """What a producer is expected to do on a quiet run.

    The two expectations are opposite, which is why this is a field and not
    an inference: a reportable rule must produce nothing, and the rules
    underneath it must produce what the corpus is known to contain.
    """

    REPORTABLE = "reportable"
    INTERMEDIATE = "intermediate"


class Outcome(str, Enum):
    """One producer's verdict on one quiet run."""

    CLEAN = "clean"
    FALSE_POSITIVE = "false_positive"
    WITHIN_BACKGROUND = "within_background"
    OUTSIDE_BACKGROUND = "outside_background"
    NOT_EXERCISED = "not_exercised"


#: The two that mean the control did not hold. `NOT_EXERCISED` is not among
#: them: an unbuilt rule is a stated gap in coverage rather than a failure
#: of the rules that do exist, and it is reported as a count of types rather
#: than folded into a pass or a fail it would misrepresent either way.
_FAILING = (Outcome.FALSE_POSITIVE, Outcome.OUTSIDE_BACKGROUND)


@dataclass(frozen=True, slots=True)
class Background:
    """What quiet runs were measured to produce, per run.

    `runs` is mandatory for the reason `anom-011`'s `Conditions` is: a band
    without the population it came from is a memory rather than a
    measurement, and it is also what sets the roughly 2/(n+1) rate at which
    a fresh run from the same distribution falls outside it.
    """

    low: int
    high: int
    runs: int
    note: str = ""

    def __post_init__(self) -> None:
        if self.low < 0:
            raise ControlError(
                f"a background floor cannot be negative, got {self.low}."
            )
        if self.high < self.low:
            raise ControlError(
                f"background top {self.high} is below its floor {self.low}, so no "
                "count can ever be within it and every quiet run would fail."
            )
        if self.runs < 1:
            raise ControlError(
                "a background measured over no runs is not a measurement. Record "
                "the number of quiet runs the band was taken over."
            )

    def holds(self, observed: int) -> bool:
        """Inclusive at both ends.

        `anom-014`'s rule: the boundary belongs to the measured value and
        not to the comparison.
        """
        return self.low <= observed <= self.high


@dataclass(frozen=True, slots=True)
class Producer:
    """One detector, and what a quiet run is expected to get from it."""

    rule_id: str
    finding_type: str
    kind: Kind
    background: Background | None = None
    built: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind is Kind.INTERMEDIATE and self.background is None:
            raise ControlError(
                f"{self.rule_id}/{self.finding_type} is an intermediate producer "
                "with no measured background. The band is what makes 'silence "
                "fails' a measurement rather than an assertion, so there is "
                "nothing to judge it against."
            )
        if self.kind is Kind.REPORTABLE and self.background is not None:
            raise ControlError(
                f"{self.rule_id}/{self.finding_type} is reportable and carries a "
                "background. Zero is this side's requirement and not a figure "
                "measured off the corpus; a band here makes a false positive "
                "negotiable."
            )

    @property
    def key(self) -> Key:
        return (self.rule_id, self.finding_type)


def build_register(*producers: Producer) -> Mapping[Key, Producer]:
    """The register as a mapping on the pair, refusing a repeated producer.

    Public because the suite builds its own register rather than asserting
    against the measured bands, and a register assembled some other way
    would not be the one the refusals are proved on.
    """
    by_key: dict[Key, Producer] = {}
    for producer in producers:
        if producer.key in by_key:
            raise ControlError(f"{producer.key} is registered twice.")
        by_key[producer.key] = producer
    return by_key


#: Every detector the control knows about. Bands measured over corpus v2's
#: twenty quiet runs -- see `measurements/corpus/quiet_run_background.log`.
REGISTER: Mapping[Key, Producer] = build_register(
    Producer(
        rule_id=RF_RULE,
        finding_type=RF_TYPE,
        kind=Kind.INTERMEDIATE,
        background=Background(
            low=0,
            high=0,
            runs=20,
            note=(
                "zero on 20 of 20. The RF grid is synthetic and a quiet run has "
                "nothing injected into it, so silence here is the correct answer "
                "and not a detector that failed to look."
            ),
        ),
    ),
    Producer(
        rule_id=GAP_RULE,
        finding_type=GAP_TYPE,
        kind=Kind.INTERMEDIATE,
        background=Background(
            low=9,
            high=19,
            runs=20,
            note=(
                "median 16.5, never zero. Replayed flight data genuinely "
                "contains discontinuities, so a run reporting none of them is a "
                "detector that did not look."
            ),
        ),
    ),
    Producer(
        rule_id=CLUSTER_RULE,
        finding_type=CLUSTER_TYPE,
        kind=Kind.INTERMEDIATE,
        background=Background(
            low=5,
            high=9,
            runs=20,
            note=(
                "median 7, never zero. Registered although no reportable rule "
                "consumes it -- anom-005 reads anom-012's rate excess instead of "
                "cluster size -- because leaving a built detector out on the "
                "grounds that nothing currently reads it is the silent gap this "
                "item exists to close."
            ),
        ),
    ),
    Producer(
        rule_id=GAP_RULE,
        finding_type=EXCESS_TYPE,
        kind=Kind.INTERMEDIATE,
        background=Background(
            low=0,
            high=0,
            runs=20,
            note=(
                "zero on 20 of 20, structurally rather than statistically: "
                "anom-012 is reached only through a zone anom-007 dismissed as "
                "environmental, so on a quiet run it is never invoked. A "
                "non-zero count means an upstream rule fired, which the "
                "reportable side reports too -- a second guard at a different "
                "boundary. It is also the register's one real key collision, "
                "sharing anom-010's rule id."
            ),
        ),
    ),
    Producer(rule_id=FAULT_RULE, finding_type=FAULT_TYPE, kind=Kind.REPORTABLE),
    Producer(rule_id=FUSION_RULE, finding_type=INTERFERENCE_TYPE, kind=Kind.REPORTABLE),
    Producer(
        rule_id=SOURCE_GAP_RULE,
        finding_type=SOURCE_GAP_TYPE,
        kind=Kind.REPORTABLE,
        built=False,
        note=(
            "anom-006 has no rule. Attempted twice, measured, and closed on the "
            "corpus as generated; recorded as future work. Registered so its "
            "silence is reported as an absent rule rather than as a clean one."
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class Verdict:
    """What one producer did on one quiet run, and whether that is allowed."""

    producer: Producer
    observed: int | None
    outcome: Outcome

    @property
    def holds(self) -> bool:
        return self.outcome not in _FAILING

    def as_json(self) -> dict[str, Any]:
        band = self.producer.background
        return {
            "rule_id": self.producer.rule_id,
            "finding_type": self.producer.finding_type,
            "kind": self.producer.kind.value,
            "observed": self.observed,
            "background": None if band is None else [band.low, band.high],
            "outcome": self.outcome.value,
        }


@dataclass(frozen=True, slots=True)
class Control:
    """One quiet run, graded per detector."""

    run_id: str
    verdicts: tuple[Verdict, ...]

    @property
    def holds(self) -> bool:
        return all(verdict.holds for verdict in self.verdicts)

    @property
    def false_positives(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.outcome is Outcome.FALSE_POSITIVE)

    @property
    def reportable_types_registered(self) -> int:
        return sum(1 for v in self.verdicts if v.producer.kind is Kind.REPORTABLE)

    @property
    def reportable_types_covered(self) -> int:
        return sum(
            1
            for v in self.verdicts
            if v.producer.kind is Kind.REPORTABLE and v.producer.built
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "holds": self.holds,
            # Quoted with the rate rather than beside it: read as three
            # reportable types, a false-positive figure overstates the
            # layer's coverage by exactly the rule that does not exist.
            "reportable_types": (
                f"{self.reportable_types_covered} of "
                f"{self.reportable_types_registered}"
            ),
            "verdicts": [verdict.as_json() for verdict in self.verdicts],
        }


def audit(
    *,
    run_id: str,
    scenario_type: str,
    counts: Mapping[Key, int],
    register: Mapping[Key, Producer] = REGISTER,
) -> Control:
    """Grade one quiet run against an account of every registered producer.

    `counts` is that account: one entry per built producer, keyed on the
    `(rule_id, finding_type)` pair. A missing entry, an unregistered one and
    an entry for a rule with no implementation are all refused, because each
    is a caller error rather than a property of the run -- and because a
    control that returns a verdict on a partial account is a control that
    passes when nothing ran.
    """
    if scenario_type != QUIET:
        raise ControlError(
            f"{scenario_type!r} is not a quiet run. This control grades "
            f"{QUIET!r} only: a run of a staged type that staged nothing is "
            "eval-002's exclusion and is counted there, since scoring it here "
            "would put a run the generator failed on into a figure about the "
            "detectors."
        )

    expected = {key for key, producer in register.items() if producer.built}
    unbuilt = {key for key, producer in register.items() if not producer.built}
    supplied = set(counts)

    missing = expected - supplied
    if missing:
        raise ControlError(
            f"these registered producers were not accounted for: {sorted(missing)}. "
            "On the reportable side zero is the required answer, so an absent "
            "producer and a correct one are indistinguishable by counting; a "
            "detector that found nothing has to say so."
        )
    unknown = supplied - set(register)
    if unknown:
        raise ControlError(
            f"these producers are not registered: {sorted(unknown)}. A detector "
            "this control has never been asked about cannot be graded by it, "
            "following anom-013's refusal of a claim whose rule has no declared "
            "position."
        )
    phantom = supplied & unbuilt
    if phantom:
        raise ControlError(
            f"counts were supplied for {sorted(phantom)}, which has no "
            "implementation. Counted output from a rule that does not exist is "
            "a caller error, not a run property."
        )

    verdicts: list[Verdict] = []
    for key in sorted(register):
        producer = register[key]
        if not producer.built:
            verdicts.append(
                Verdict(producer=producer, observed=None, outcome=Outcome.NOT_EXERCISED)
            )
            continue

        observed = counts[key]
        if observed < 0:
            raise ControlError(f"{key} reported a negative count of {observed}.")

        if producer.kind is Kind.REPORTABLE:
            outcome = Outcome.CLEAN if observed == 0 else Outcome.FALSE_POSITIVE
        else:
            band = producer.background
            assert band is not None  # guaranteed by Producer.__post_init__
            outcome = (
                Outcome.WITHIN_BACKGROUND
                if band.holds(observed)
                else Outcome.OUTSIDE_BACKGROUND
            )
        verdicts.append(Verdict(producer=producer, observed=observed, outcome=outcome))

    return Control(run_id=run_id, verdicts=tuple(verdicts))
