"""Track-gap detection sensitivity, and the recall the fusion rules rest on.
Spec: anom-011.

Every rule above `anom-010` assumes that when the generator stages a
disruption on an aircraft, the detector notices. Measured on the stored
batch, it notices about one in five, and that single number is why
`anom-004` cannot separate a staged run from its control and why `anom-005`
would report an interference zone on seventy per cent of the runs whose
truth is a sensor fault.

This module turns that figure into an account. It adds no rule and changes
no detection: it asks `anom-010` for its own reasons through
`explain_track_gaps` and scores them against the answer key `scn-002`
recorded at generation time.

**Two constraints from the item are enforced here rather than reviewed.**
A `Recall` whose losses do not account for every undetected aircraft is
refused at construction, so an attribution cannot be asserted without being
counted. And the policy fields of `Conditions` are overwritten from the
policy actually used rather than trusted from the caller, because a figure
whose recorded conditions could disagree with the measurement is worse than
one carrying no conditions at all.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum

from app.dal.models import CanonicalObservation
from app.detection.track_gap import GapPolicy, Rejection, explain_track_gaps


class Loss(str, Enum):
    """Where a staged aircraft went.

    Every `Rejection` the rule can give, plus the one it cannot: an
    aircraft the generator recorded as staged that never appears in the
    run's observations at all. That is a real failure with a different
    cause from all the others, and dropping it from the denominator would
    flatter the figure.
    """

    NOT_IN_RUN = "not_in_run"
    NO_PAIR = Rejection.NO_PAIR.value
    BELOW_THRESHOLD = Rejection.BELOW_THRESHOLD.value
    ON_GROUND = Rejection.ON_GROUND.value
    NOT_INTERIOR = Rejection.NOT_INTERIOR.value
    POSITION_NOT_STALE = Rejection.POSITION_NOT_STALE.value
    CONTACT_NOT_FRESH = Rejection.CONTACT_NOT_FRESH.value


@dataclass(frozen=True, slots=True)
class Conditions:
    """What a recall figure is a figure *of*.

    Mandatory, because this project has already been caught quoting a
    measurement without them: a timing figure taken by a script that no
    longer existed, recorded as three different numbers in three
    documents, and impossible to re-derive. A figure without its conditions
    is a memory.

    The policy fields are filled in by `measure_recall` from the policy it
    actually ran, so a caller cannot retype them wrongly.
    """

    batch: str
    scenario_type: str
    runs: int
    threshold_s: float | None = None
    contact_fresh_within_s: float | None = None
    interior_margin_deg: float | None = None


@dataclass(frozen=True, slots=True)
class Recall:
    """How many staged aircraft the rule found, and where the rest went."""

    conditions: Conditions
    staged: int
    detected: int
    losses: Mapping[Loss, int]

    def __post_init__(self) -> None:
        missed = self.staged - self.detected
        counted = sum(self.losses.values())
        if counted != missed:
            raise ValueError(
                f"losses account for {counted} of {missed} undetected aircraft. "
                "anom-011 forbids naming where a staged aircraft went without "
                "counting it, so a tally that does not add up is refused here "
                "rather than published."
            )

    @property
    def rate(self) -> float:
        return self.detected / self.staged


def measure_recall(
    *,
    staged_aircraft: Iterable[str],
    observations: Iterable[CanonicalObservation],
    policy: GapPolicy,
    conditions: Conditions,
) -> Recall:
    """Score `TRACK-GAP` against the answer key for one run.

    Against ground truth, never against the detector's own output: a staged
    aircraft the rule said nothing about is a miss, not an absence from the
    denominator. `api-009` keeps the answer key out of the observations
    precisely so this comparison has to be made deliberately.

    A run that staged nothing is refused rather than scored. One seed in
    the stored batch staged zero aircraft across all three of its runs;
    calling that nought per cent would drag an average down for a reason
    with nothing to do with the detector, and calling it a hundred would do
    the reverse. It has to be excluded by the caller, visibly.
    """
    staged = set(staged_aircraft)
    if not staged:
        raise ValueError(
            "this run staged nothing, so its recall is undefined. Exclude it "
            "deliberately rather than scoring it as none or all."
        )

    verdicts = {v.aircraft_id: v for v in explain_track_gaps(observations, policy)}

    detected = 0
    losses: Counter[Loss] = Counter()
    for aircraft in sorted(staged):
        verdict = verdicts.get(aircraft)
        if verdict is None:
            losses[Loss.NOT_IN_RUN] += 1
        elif verdict.detected:
            detected += 1
        else:
            # One loss per aircraft, so the tally adds up: the reason it got
            # furthest on, which `anom-010` orders for exactly this.
            losses[Loss(verdict.rejections[0].value)] += 1

    return Recall(
        conditions=replace(
            conditions,
            threshold_s=policy.threshold.total_seconds(),
            contact_fresh_within_s=policy.contact_fresh_within.total_seconds(),
            interior_margin_deg=policy.interior_margin_deg,
        ),
        staged=len(staged),
        detected=detected,
        losses=dict(losses),
    )
