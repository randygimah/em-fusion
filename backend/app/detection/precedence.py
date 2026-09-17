"""Reportable rule precedence. Spec: anom-013.

The three reportable rules are not three independent tests. They are one
question asked three times in a fixed order, and the order is the whole
content of this module.

**Why an order is needed at all.** With the rules testing independently, a
background cluster of aircraft dropouts lies within the fusion radius on 14
of 20 runs whose truth is a broken receiver, so `anom-005` claims most of
`anom-007`'s runs -- and because `anom-006` is defined never to speak about
an event fusion has claimed, the wrong answer does not merely get added
alongside the right one. **It takes the event away from the rule that would
have been right.** Deciding the equipment fault first removes that question
rather than answering it with weaker evidence.

**Why this order.** `anom-001` separates an 8 dB elevation from a baseline
spread of about 1.5 dB, beyond five sigma, and `anom-007` decides on that
pattern alone with no track evidence at all. `anom-012`'s rate excess
reaches a Youden's J of 0.40 over 40 matched pairs. Asking the weaker
signal to arbitrate what the stronger one already settles is the error, and
ordering deletes the question rather than answering it.

**It resolves claims, not rules.** Each rule emits a bid for a zone; this
orders the bids by the declared constant below and hands back at most one
per zone with a ledger of what was suppressed and by whom. That shape is
what lets this be finished before `anom-006` and `anom-005` exist -- their
only obligation to it is to emit a claim, and nothing here changes when
they arrive. A resolver that called the three rules itself could not be
built before them and would have to be proved against stubs, which is the
arrangement that let `anom-007` pass thirty-six tests and a mutation pass
while being wrong about the corpus.

**Suppression is between rules and never within one.** Two claims from the
same rule are two events: two broken receivers are two broken receivers,
and a run may hold both. The exclusion this module makes enforceable is
`anom-006`'s with `anom-005`, which is cross-rule by construction.

**What it does not yet do.** Only `anom-007` produces claims today, so the
ladder cannot be measured end to end until `anom-005` lands. What is
already measured: of the 120 runs in batches 2 and 3, those reaching a
fusion decision at all are 40 of 40 `gnss-degradation`, 0 of 40
`aircraft-coverage-gap` and 1 of 40 `rf-sensor-fault`. The ordering already
does the work this module was written to do -- but as a property of what
the rules happen to produce rather than of a declaration anything checks,
which is the argument for writing it down rather than against.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.dal.models import Location
from app.detection.sensor_fault import RULE_ID as FAULT_RULE_ID
from app.detection.sensor_fault import SensorFaultFindings
from app.scenario.layout import RfLayout, great_circle_km

#: The declared order. `anom-007` first, because it decides on the radio
#: pattern alone and consults no track evidence; then `anom-006`, which
#: applies where there is track evidence and no co-located radio anomaly;
#: then `anom-005`, which gets what remains -- a radio anomaly spanning
#: more than one receiver with track evidence beside it.
#:
#: The order lives here and nowhere else. An implementation that resolved
#: in the order claims happened to arrive would pass every ordinary test
#: and be wrong exactly when two rules disagree, which is the only time it
#: matters.
RULE_ORDER: tuple[str, ...] = ("SENSOR-FAULT", "SOURCE-GAP", "FUSION-SPATIAL")

#: When two claims are near enough to be one event. Defaults to the
#: layout's own discrimination radius, which `scn-005` validates as the
#: distance over which one cause can reach two receivers and which
#: `anom-007` already uses for that reason.
#:
#: Deliberately *not* `anom-012`'s 60 km: that answers how wide a patch to
#: count dropouts over, which is a different question from whether two
#: candidates are one event. Provisional, and recorded as such on the item
#: -- an `anom-005` zone may span a centre and its neighbours, up to about
#: 120 km across, and two claims at opposite ends of one incident would
#: then fail this test. It is revisited when `anom-005` produces a zone,
#: rather than guessed now against a rule that does not exist.
_LAYOUT_DEFAULT = object()


class PrecedenceError(ValueError):
    """The ladder was asked for something it could only answer misleadingly."""


@dataclass(frozen=True, slots=True)
class Zone:
    """Where and when a candidate anomaly sits.

    A point and an interval, not an area. `anom-001` locates a radio
    anomaly at the reporting receiver and nowhere else, and inventing an
    extent here would claim ground nothing was observed across -- the same
    argument `db-009`'s hull makes for a group of one.
    """

    centre: Location
    started_at: datetime
    ended_at: datetime

    def __post_init__(self) -> None:
        if self.ended_at < self.started_at:
            raise PrecedenceError(
                f"zone ends before it starts: {self.started_at} to "
                f"{self.ended_at}. An inverted window overlaps nothing or "
                "everything depending on which comparison is written first."
            )

    def overlaps(self, other: Zone) -> bool:
        """Inclusive at both endpoints.

        A window's end is its last contributing reading rather than the
        first quiet one (`anom-007`), so two windows meeting at an instant
        shared it. A strict test would let a later rule claim a zone an
        earlier one had just finished with.
        """
        return self.started_at <= other.ended_at and other.started_at <= self.ended_at


@dataclass(frozen=True, slots=True)
class Claim:
    """One rule's bid for one zone.

    It carries no severity and no confidence: the ladder decides *which*
    answer is given, never how strongly, and a referee that could weigh the
    bids would be a fourth rule pretending not to be one.
    """

    rule_id: str
    anomaly_type: str
    zone: Zone


@dataclass(frozen=True, slots=True)
class Suppression:
    """A claim that was never offered its zone, and who took it.

    The ledger `evb-001` reads: "fusion was not offered this zone because
    the receiver-fault rule claimed it" is a sentence the bundle needs, and
    a suppression a reader cannot trace is an assertion.
    """

    claim: Claim
    claimed_by: str
    reason: str


@dataclass(frozen=True, slots=True)
class PrecedencePolicy:
    """How near two claims must be to count as one zone."""

    zone_radius_km: float | None = None

    def __post_init__(self) -> None:
        if self.zone_radius_km is not None and self.zone_radius_km <= 0:
            raise PrecedenceError(
                f"zone radius must be positive, got {self.zone_radius_km}. At "
                "zero every claim is its own zone, nothing is ever suppressed, "
                "and the ladder silently stops doing the one thing it exists "
                "to do."
            )

    def radius_for(self, layout: RfLayout) -> float:
        if self.zone_radius_km is None:
            return layout.discrimination_radius_km
        return self.zone_radius_km


@dataclass(frozen=True, slots=True)
class Resolution:
    """At most one answer per zone, and the record of what was refused."""

    reported: tuple[Claim, ...] = ()
    suppressed: tuple[Suppression, ...] = ()


def resolve(
    claims: Iterable[Claim], layout: RfLayout, policy: PrecedencePolicy
) -> Resolution:
    """At most one reportable anomaly per zone, in the declared order.

    Deterministic, and deliberately independent of the order the claims
    arrive in: that independence is the property the item exists to
    guarantee, so it is established here by sorting on `RULE_ORDER` rather
    than by relying on any caller to hand them over correctly.
    """
    radius = policy.radius_for(layout)
    ranked = sorted(_checked(claims), key=_position)

    reported: list[Claim] = []
    suppressed: list[Suppression] = []

    for candidate in ranked:
        taken = _taken_by(candidate, reported, radius)
        if taken is None:
            reported.append(candidate)
            continue
        suppressed.append(
            Suppression(
                claim=candidate,
                claimed_by=taken,
                reason=(
                    f"{taken} claimed this zone first, and a zone claimed by an "
                    "earlier rule is not offered to a later one -- otherwise the "
                    "weaker evidence decides what the stronger evidence has "
                    "already settled"
                ),
            )
        )

    return Resolution(reported=tuple(reported), suppressed=tuple(suppressed))


def _checked(claims: Iterable[Claim]) -> list[Claim]:
    checked = list(claims)
    for candidate in checked:
        if candidate.rule_id not in RULE_ORDER:
            raise PrecedenceError(
                f"{candidate.rule_id} has no declared position in {RULE_ORDER}. "
                "Giving it one implicitly -- last, or by the order it arrived "
                "in -- would make the outcome a property of the file rather "
                "than of the declaration."
            )
    return checked


def _position(candidate: Claim) -> tuple[int, datetime, str]:
    # Rule first, then time and type, so that two claims from one rule come
    # back in a stable order without the rule's own position depending on
    # anything but the declaration.
    return (
        RULE_ORDER.index(candidate.rule_id),
        candidate.zone.started_at,
        candidate.anomaly_type,
    )


def _taken_by(candidate: Claim, reported: list[Claim], radius: float) -> str | None:
    """Which earlier rule already holds this zone, if any.

    Same-rule claims are skipped: two broken receivers are two events, and
    suppressing within a rule would quietly cap every rule at one finding
    per run.
    """
    for held in reported:
        if held.rule_id == candidate.rule_id:
            continue
        if not held.zone.overlaps(candidate.zone):
            continue
        distance = great_circle_km(
            held.zone.centre.lat,
            held.zone.centre.lon,
            candidate.zone.centre.lat,
            candidate.zone.centre.lon,
        )
        if distance <= radius:
            return held.rule_id
    return None


def claims_from_sensor_faults(
    findings: SensorFaultFindings, layout: RfLayout
) -> tuple[Claim, ...]:
    """`anom-007`'s output as claims. The only producer that exists today.

    Only faults become claims. A dismissal is not a claim, whichever of the
    two verdicts it carries: an environmental one is precisely the case
    `anom-005` exists for, and an undecided one means what it says -- a
    rule that could not tell must not thereby block the rules that might.
    """
    del layout  # the fault already carries the receiver's position
    return tuple(
        Claim(
            rule_id=FAULT_RULE_ID,
            anomaly_type=fault.anomaly_type,
            zone=Zone(
                centre=fault.location,
                started_at=fault.started_at,
                ended_at=fault.ended_at,
            ),
        )
        for fault in findings.faults
    )
