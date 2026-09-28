"""Detection latency, in simulated time. Spec: anom-009.

**The definition is the whole item**, and the obvious one does not survive
contact with what was built. "When the detector noticed, minus when the
event began" has no second term here: detection is batch, the rules read a
completed run out of the store, and there is no instant at which a rule
emits. Written before that was settled, the measurement would have reached
for whichever timestamp was nearest to hand and produced a plausible number
measuring nothing -- and the nearest one is a stored bundle's `created_at`,
which is wall clock in a simulated-time costume and is precisely the failure
case the item names.

What is real is **how much of an incident must elapse before the evidence a
rule demands is complete**. A rule requiring ten seconds of sustained
deviation cannot honestly commit before ten seconds have passed, whatever
its implementation. That is a property of the rule's *design*, it is the
same quantity a streaming version would face, and it is therefore the figure
a thesis about deterministic rules should report -- provided it is never
described as how fast the software is.

**Where the declaration lives, and why it is not a field on the claim.** The
item says the claiming rule declares its own decidable instant, and two
facts about the built rules make a field computed at construction the wrong
shape. The rules do not retain the evidence they rest on: a `SensorFault`
carries which neighbours were asked and how far each sat from its baseline,
an `InterferenceZone` carries a rate excess and a corroboration verdict --
derived evidence, deliberately, because those objects carry conclusions
rather than readings. Neither holds the `anom-001` episodes underneath. So
the declaration is a **registry keyed on rule id**, stating how many
receivers' evidence that rule requires, and a rule with no entry is refused
rather than defaulted -- `anom-013`'s own rule that a claim whose rule has
no declared position is refused rather than appended.

**Why the count, and not a formula.** `anom-005`'s zone window is the
**union** of its receivers' windows, earliest start to latest end. So
`window start + minimum` is right for `anom-007` and *wrong* for `anom-005`:
at the union's start only the first receiver has begun, while the rule's
whole claim is that more than one deviated together. One formula for both
would have understated interference latency by however long the receivers
were staggered -- silently, and plausibly.

Nothing here reads a clock, opens a database, or takes an argument that
could carry one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence

from app.detection.fusion import RULE_ID as FUSION_RULE_ID
from app.detection.precedence import Claim, PrecedenceError
from app.detection.rf_noise import DEFAULT_MINIMUM_DURATION, RfNoiseAnomaly
from app.detection.sensor_fault import RULE_ID as FAULT_RULE_ID

#: How many receivers' evidence each rule must have before it can commit.
#:
#: This is the rules' own requirement written down, and it is a **count**
#: rather than a formula because the two rules differ in exactly this way:
#: a broken receiver is a claim about one instrument, while interference is
#: a claim that more than one deviated together. Getting it wrong is not
#: visible in the output -- both produce a plausible number of seconds.
#:
#: A rule absent from this table is **refused**. A default of one would
#: measure a new multi-receiver rule as though it needed a single receiver,
#: which is a number answering a question nobody asked.
RECEIVERS_REQUIRED: Mapping[str, int] = {
    FAULT_RULE_ID: 1,
    FUSION_RULE_ID: 2,
}


@dataclass(frozen=True, slots=True)
class Latency:
    """One claim's latency, with everything needed to read it correctly."""

    rule_id: str
    #: The staged incident's true start, off the answer key.
    onset: datetime
    #: The earliest simulated instant at which the rule's evidence was
    #: complete. Never a wall-clock time and never a stored row's timestamp.
    decidable_at: datetime
    #: **Signed, and never clamped.** A negative value means the rule's
    #: evidence begins before the staged onset -- it swept in readings from
    #: outside the incident -- and clamping to zero would read as instant
    #: detection, which is the opposite of what it says.
    latency: timedelta
    #: Carried so the figure cannot be quoted without its resolution: the
    #: value is quantised to the run's sampling interval, and this is the
    #: evidence span that sets its floor.
    minimum: timedelta
    #: Which receivers' evidence was counted, in the order they qualified.
    contributing: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "onset": self.onset.isoformat(),
            "decidable_at": self.decidable_at.isoformat(),
            "latency_seconds": self.latency.total_seconds(),
            "minimum_seconds": self.minimum.total_seconds(),
            "contributing": list(self.contributing),
        }


def measure(
    claim: Claim,
    *,
    sensors: Sequence[str],
    onset: datetime,
    episodes: Iterable[RfNoiseAnomaly],
    minimum: timedelta = DEFAULT_MINIMUM_DURATION,
) -> Latency:
    """This claim's latency against the incident it reports.

    `sensors` comes from the finding that produced the claim -- a
    `SensorFault`'s own receiver, or an `InterferenceZone`'s list -- because
    a `Claim` carries a centre and a window and not the receivers behind
    them. `episodes` is the run's `anom-001` output; episodes on receivers
    this claim is not about are ignored rather than refused, since a run
    holds every receiver's.
    """
    if minimum < timedelta(0):
        raise PrecedenceError(
            f"the minimum evidence duration is {minimum}, which is negative. "
            "It would place every decidable instant earlier than the evidence "
            "that produced it, and the latencies would be short by that much "
            "with nothing in the output saying so."
        )

    required = RECEIVERS_REQUIRED.get(claim.rule_id)
    if required is None:
        raise PrecedenceError(
            f"rule {claim.rule_id!r} declares no receiver requirement, so "
            "there is no saying when its evidence was complete. Add it to "
            "RECEIVERS_REQUIRED rather than letting it default: a default of "
            "one would measure a rule that needs several as though it needed "
            "the first, which produces a plausible number for a question "
            "nobody asked."
        )

    wanted = set(sensors)
    qualified: dict[str, datetime] = {}
    for episode in episodes:
        sensor = episode.cell.sensor_id
        if sensor not in wanted:
            continue
        # A receiver qualifies on its **earliest** episode: that is when its
        # evidence first became sufficient, and a later one adds nothing to
        # a question about when the rule could first have decided.
        at = episode.started_at + minimum
        if sensor not in qualified or at < qualified[sensor]:
            qualified[sensor] = at

    if len(qualified) < required:
        raise PrecedenceError(
            f"{claim.rule_id} requires {required} receiver(s) with evidence "
            f"and {len(qualified)} of {len(wanted)} had any. The evidence the "
            "rule says it needs was never present, so a latency computed "
            "anyway would describe nothing."
        )

    # The nth earliest qualification, n being what the rule requires. For a
    # single-receiver rule that is simply its own; for `anom-005` it is the
    # instant the second receiver's evidence became sufficient, which is the
    # earliest moment "more than one deviated together" was supportable.
    order = sorted(qualified.items(), key=lambda pair: (pair[1], pair[0]))
    decidable_at = order[required - 1][1]

    return Latency(
        rule_id=claim.rule_id,
        onset=onset,
        decidable_at=decidable_at,
        latency=decidable_at - onset,
        minimum=minimum,
        contributing=tuple(sensor for sensor, _ in order[:required]),
    )


__all__ = [
    "RECEIVERS_REQUIRED",
    "Latency",
    "measure",
]
