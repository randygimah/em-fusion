"""The fusion rule, `FUSION-SPATIAL`. Spec: anom-005.

The last step of `anom-013`'s ladder, and the rule whose design changed
most under measurement. As first specified it required a radio anomaly
*and* co-located track evidence -- both conditions necessary. It now fires
on the radio pattern alone and carries the track evidence beside it.

**Why the gate went.** Under the ordering this rule sees almost nothing but
real interference. Measured over 240 runs, the zones reaching it are 40 of
40 `gnss-degradation`, 0 of 40 `aircraft-coverage-gap`, 0 of 20
`normal-baseline` and 1 of 40 `rf-sensor-fault` -- and that single leak
carries a zero-length window and cannot be measured. A gate at the
pre-registered threshold would have reported 26 of the 40 and rejected
nothing, because nothing false arrives here. The 14 it would have lost all
hold four or fewer track findings across the whole run, against a median
ratio of 3.87 over all 40: they are zones with almost no aircraft in them,
not zones with weak evidence. The gate would have suppressed an
interference report backed by an 8 dB deviation because few aircraft
happened to be flying nearby, which is a property of where the generator
put the zone and not evidence about whether anything happened.

**Why confidence does not follow the excess either.** That was this item's
own first correction and it was the same error softened: a signal reaching
a Youden's J near 0.3 must not grade a claim an 8 dB deviation establishes.
By the time this rule fires, `anom-007` has declined the zone as
environmental -- a deviation past threshold on more than one receiver,
beyond five sigma against a baseline spread of about 1.5 dB. So confidence
has a floor of Medium that the track side cannot breach and rises to High
only on corroboration. **This rule never emits Low**, and that is recorded
rather than left as a branch nobody notices.

Nor is confidence taken from the radio side's own gradations, because
measured they do not vary: the zone spans 2 receivers in 34 of 40 runs and
3 in the rest, and the peak deviation runs 11.9 to 15.9 dB, which
`anom-001` grades Medium in 35 and High in 5. `scn-002` stages one incident
of one size, so the corpus cannot exercise a severity gradation here at
all.

**Three corroboration states, not two.** `anom-012` adds a smoothing term
of one finding per run span to both rates, so a period holding no findings
has a rate consisting of nothing but that constant and the ratio is a
function of the period lengths rather than a comparison of two observed
rates. Measured, that is the majority case: of the 26 zones whose excess
reaches the threshold, only 6 hold a finding in both periods. A disc with
nothing in it during the window is not a disc that showed no disruption --
the third place in this layer where silence had to be separated from
evidence of absence, after `anom-001`'s unjudged cells and `anom-007`'s
unmeasurable neighbours.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy.orm import Session, sessionmaker

from app.dal.models import Location
from app.detection.precedence import Claim, Zone
from app.detection.rate_excess import ExcessPolicy, RateExcess, measure_rate_excess
from app.detection.sensor_fault import Dismissal, SensorFaultFindings, Verdict
from app.scenario.layout import RfLayout

#: Travels with every anomaly this rule raises (FR-402).
RULE_ID = "FUSION-SPATIAL"

#: `possible_`, because the rule reports evidence to an analyst and does
#: not conclude (FR-305).
ANOMALY_TYPE = "possible_interference_zone"

#: The excess at which the track side corroborates. This is the value
#: batch 2 chose and batch 3 was scored against out of sample, carried here
#: rather than refitted -- a threshold chosen on the data it is scored
#: against is fitted to that data.
#:
#: It is a corroboration boundary and **not** a gate. See the module
#: docstring: as a gate it would have cost 14 of 40 true reports and
#: rejected nothing.
DEFAULT_CORROBORATION_THRESHOLD = 1.58


class Corroboration(str, Enum):
    """What the track side had to say, in three values rather than two."""

    CORROBORATED = "corroborated"
    #: Measured over two populated periods, and below the threshold.
    NOT_CORROBORATED = "not_corroborated"
    #: No measurement was possible. Not the same as a measurement of
    #: nothing, and never to be read as one.
    NOT_MEASURABLE = "not_measurable"


class Confidence(str, Enum):
    """Low, Medium or High -- never a percentage and never a decimal.

    `LOW` is unreachable from this rule and exists because `ui-001` fixes
    the vocabulary for anything an analyst sees. The floor is Medium and it
    comes from the radio evidence; see the module docstring.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class FusionPolicy:
    """What counts as corroboration, and how wide a patch to look over."""

    corroboration_threshold: float = DEFAULT_CORROBORATION_THRESHOLD
    #: `None` defers to `anom-012`'s own chosen radius, which carries its
    #: reasoning; this exists so a caller can vary it without this module
    #: holding a second copy of that number.
    excess_radius_km: float | None = None


@dataclass(frozen=True, slots=True)
class Assessment:
    """What the track side contributed, and why.

    Carries no severity and no score: confidence is the only graded field
    and it is words (`ui-001`).
    """

    corroboration: Corroboration
    confidence: Confidence
    reason: str


@dataclass(frozen=True, slots=True)
class InterferenceZone:
    """One place and period where more than one receiver deviated together."""

    #: The receivers whose deviation defines the zone, the subject first.
    sensors: tuple[str, ...]
    centre: Location
    started_at: datetime
    ended_at: datetime
    corroboration: Corroboration
    confidence: Confidence
    #: The measurement whole, counts included, or `None` where none could
    #: be taken. The counts are what say whether the ratio is a rate
    #: comparison at all, so carrying the ratio alone would be carrying a
    #: number that cannot be checked.
    excess: RateExcess | None
    reason: str
    anomaly_type: str = ANOMALY_TYPE
    rule_id: str = RULE_ID


@dataclass(frozen=True, slots=True)
class Declination:
    """A zone this rule looked at and did not claim, and why."""

    sensors: tuple[str, ...]
    started_at: datetime
    ended_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class InterferenceFindings:
    """What the rule concluded, including what it declined to conclude."""

    zones: tuple[InterferenceZone, ...] = ()
    declined: tuple[Declination, ...] = ()


def assess(excess: RateExcess | None, policy: FusionPolicy) -> Assessment:
    """What the track side contributes to a zone the radio side established.

    Pure: no database and no clock, so the arithmetic that decides an
    analyst-visible word can be tested without Docker.
    """
    if excess is None:
        return Assessment(
            corroboration=Corroboration.NOT_MEASURABLE,
            confidence=Confidence.MEDIUM,
            reason=(
                "no rate could be taken over this zone, so the track side "
                "contributes nothing either way; the radio evidence stands alone"
            ),
        )

    if excess.during == 0 or excess.outside == 0:
        empty = "window" if excess.during == 0 else "reference period"
        return Assessment(
            corroboration=Corroboration.NOT_MEASURABLE,
            confidence=Confidence.MEDIUM,
            reason=(
                f"the {empty} holds no track findings, so its rate is nothing but "
                "the smoothing constant and the ratio compares one observed rate "
                "against an assumption. A disc with nothing in it is not a disc "
                "that showed no disruption."
            ),
        )

    if excess.ratio >= policy.corroboration_threshold:
        return Assessment(
            corroboration=Corroboration.CORROBORATED,
            confidence=Confidence.HIGH,
            reason=(
                f"track discontinuities ran {excess.ratio:.2f} times their local "
                f"rate during this window ({excess.during} inside against "
                f"{excess.outside} outside), at or above the "
                f"{policy.corroboration_threshold:g} the replication set"
            ),
        )

    return Assessment(
        corroboration=Corroboration.NOT_CORROBORATED,
        confidence=Confidence.MEDIUM,
        reason=(
            f"track discontinuities ran {excess.ratio:.2f} times their local rate "
            f"({excess.during} inside against {excess.outside} outside), below the "
            f"{policy.corroboration_threshold:g} the replication set, so the track "
            "side does not corroborate. The radio evidence is unaffected."
        ),
    )


def detect_interference(
    faults: SensorFaultFindings,
    session_factory: sessionmaker[Session],
    *,
    scenario_run_id: int,
    run_span: tuple[datetime, datetime],
    layout: RfLayout,
    policy: FusionPolicy,
) -> InterferenceFindings:
    """Interference zones, from what `anom-007` declined as environmental.

    That declination *is* the finding that more than one receiver deviated
    together, which is what an interference zone is, so this rule does not
    repeat the neighbour test -- it consumes its verdict.

    **One event, one zone.** An incident spanning two receivers has both of
    them dismissed as environmental, each naming the other, so one zone per
    dismissal reports the same event twice -- measured, 160 zones from 60
    staged runs before this was fixed. The dismissals are therefore merged
    into events first, on `anom-007`'s own finding of which receivers
    deviated together rather than by re-deriving distance here. That also
    makes `anom-013`'s cross-rule-only suppression safe: the ladder will
    not merge two claims from this rule, deliberately, so this rule must
    not produce two for one event.

    Deterministic, and deliberately not by trusting the caller: the
    dismissals are sorted here, so the property is established by this
    module rather than inherited from whoever assembled its input. The
    same argument `anom-013` makes about arrival order, one layer down.
    """
    zones: list[InterferenceZone] = []
    declined: list[Declination] = []

    ordered = sorted(
        faults.dismissed, key=lambda d: (d.started_at, d.ended_at, d.sensor_id)
    )

    for dismissal in ordered:
        if dismissal.verdict is Verdict.ENVIRONMENTAL:
            continue
        declined.append(
            Declination(
                sensors=(dismissal.sensor_id, *dismissal.spatial.abnormal),
                started_at=dismissal.started_at,
                ended_at=dismissal.ended_at,
                reason=(
                    f"the receiver-fault rule returned {dismissal.verdict.value} "
                    "for this zone, so nothing has established that the "
                    "deviation reached more than one receiver. Reporting an "
                    "interference zone would claim more than the evidence "
                    f"supports: {dismissal.reason}"
                ),
            )
        )

    environmental = [d for d in ordered if d.verdict is Verdict.ENVIRONMENTAL]
    for event in _events(environmental):
        # Every receiver known to have deviated: the ones assessed, and
        # the neighbours their evidence named abnormal. A receiver can be
        # named without being assessed itself, and leaving it out would
        # under-report the extent of the zone.
        sensors = tuple(
            sorted(
                {d.sensor_id for d in event}
                | {other for d in event for other in d.spatial.abnormal}
            )
        )
        started_at = min(d.started_at for d in event)
        ended_at = max(d.ended_at for d in event)
        centre = _centre(sensors, layout)
        excess = _excess(
            session_factory,
            scenario_run_id=scenario_run_id,
            centre=centre,
            window=(started_at, ended_at),
            run_span=run_span,
            policy=policy,
        )
        assessment = assess(excess, policy)
        zones.append(
            InterferenceZone(
                sensors=sensors,
                centre=centre,
                started_at=started_at,
                ended_at=ended_at,
                corroboration=assessment.corroboration,
                confidence=assessment.confidence,
                excess=excess,
                reason=assessment.reason,
            )
        )

    return InterferenceFindings(zones=tuple(zones), declined=tuple(declined))


def _events(dismissals: list[Dismissal]) -> list[list[Dismissal]]:
    """Dismissals grouped into the events they describe.

    Two belong together when either names the other's receiver as abnormal
    and their windows overlap. Either, not both: the layout makes distance
    symmetric so two assessed receivers normally name each other, and the
    rule does not depend on that holding -- a one-directional test would
    silently split an event the moment it did not.

    Membership chains, so a deviation reaching three receivers is one event
    even where the outer two never name each other
    -- the same transitive grouping `db-009` does over findings, on the
    evidence `anom-007` already produced rather than on a distance measured
    a second time here.

    Overlap is inclusive at both endpoints, on `anom-007`'s argument: a
    window's end is its last contributing reading, so two meeting at an
    instant shared it.
    """
    groups: list[list[Dismissal]] = []
    for dismissal in dismissals:
        joined = [i for i, group in enumerate(groups) if _same_event(dismissal, group)]
        # Chaining: one dismissal can join several groups that were
        # separate until it arrived, so every group it touches is absorbed
        # rather than only the first.
        merged = [dismissal, *(d for i in joined for d in groups[i])]
        groups = [group for i, group in enumerate(groups) if i not in joined]
        groups.append(merged)

    # Members and groups both sorted, so the reported order is a property
    # of the evidence rather than of the order the dismissals were walked
    # in -- and so that reading one member of a group is never a way to
    # learn something about the group as a whole.
    ordered = [sorted(group, key=_member_order) for group in groups]
    return sorted(ordered, key=lambda group: _member_order(group[0]))


def _member_order(dismissal: Dismissal) -> tuple[datetime, datetime, str]:
    return (dismissal.started_at, dismissal.ended_at, dismissal.sensor_id)


def _same_event(dismissal: Dismissal, group: list[Dismissal]) -> bool:
    return any(
        (
            member.sensor_id in dismissal.spatial.abnormal
            or dismissal.sensor_id in member.spatial.abnormal
        )
        and dismissal.started_at <= member.ended_at
        and member.started_at <= dismissal.ended_at
        for member in group
    )


def _centre(sensors: tuple[str, ...], layout: RfLayout) -> Location:
    """The middle of the receivers that saw it.

    A zone spanning two receivers is centred between them and not on
    whichever was assessed first: this is what `anom-012`'s disc is
    measured around, so taking one end would measure a patch offset from
    the event by half its width. A plain mean rather than a spherical
    centroid, because the layout spans under 250 km and the difference is
    metres against a disc tens of kilometres wide -- and unlike `db-009`'s
    centroid this is never persisted or compared against a radius, so the
    approximation cannot accumulate.
    """
    sites = [layout.site(sensor_id) for sensor_id in sensors]
    return Location(
        lat=sum(site.lat for site in sites) / len(sites),
        lon=sum(site.lon for site in sites) / len(sites),
    )


def _excess(
    session_factory: sessionmaker[Session],
    *,
    scenario_run_id: int,
    centre: Location,
    window: tuple[datetime, datetime],
    run_span: tuple[datetime, datetime],
    policy: FusionPolicy,
) -> RateExcess | None:
    """The track side's measurement, or `None` where none can be taken.

    `anom-012` refuses a window of no length or one covering the whole run,
    and 6 of 86 runs produce the first. Those refusals are about the track
    measurement and say nothing about the radio evidence, so they are
    turned into an absent measurement rather than propagated.
    """
    excess_policy = (
        ExcessPolicy()
        if policy.excess_radius_km is None
        else ExcessPolicy(radius_km=policy.excess_radius_km)
    )
    try:
        return measure_rate_excess(
            session_factory,
            scenario_run_id=scenario_run_id,
            centre=centre,
            policy=excess_policy,
            window=window,
            run_span=run_span,
        )
    except ValueError:
        return None


def claims_from_interference(
    findings: InterferenceFindings,
) -> tuple[Claim, ...]:
    """This rule's zones as claims for `anom-013`.

    Its only obligation to the precedence. A declined zone is not a claim:
    this rule did not conclude anything about it, and offering it would
    make the ladder report what the rule declined to.
    """
    return tuple(
        Claim(
            rule_id=RULE_ID,
            anomaly_type=zone.anomaly_type,
            zone=Zone(
                centre=zone.centre,
                started_at=zone.started_at,
                ended_at=zone.ended_at,
            ),
        )
        for zone in findings.zones
    )
