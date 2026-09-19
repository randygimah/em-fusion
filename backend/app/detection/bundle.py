"""Evidence bundles. Spec: evb-001.

The boundary around everything after Phase 8, and **a containment boundary
rather than a container**. It is the only thing the AI layer ever receives,
which is what makes `ai-008`'s grounding check tractable at all: asking
"does this claim cite something real" against 20.7M observations has no
computable answer, and against a closed list of evidence items it is a set
membership test.

**The unit is one reported claim.** Not one run -- a run staging two broken
receivers is two events, and `anom-013` already refuses to merge them
because its suppression is cross-rule only, so grouping by run would
quietly cap every run at one bundle. Not one finding -- that is the
fragmentation this item exists to prevent.

**This module does not group on time or space.** That grouping is
`anom-013`'s, it is measured, and a second implementation here would be a
second copy of a rule that already exists -- the trap this repository
recorded once when distance was nearly measured in two places. What is
genuinely this module's is the **frequency** axis: `anom-001` raises
episodes per sensor *per channel*, nothing upstream merges them, and a wide
event arrives as several episodes that must become one bundle.

**Every absence is typed.** *Not applicable*, *not measurable* and
*measured and found nothing* are three different statements, and a consumer
that cannot tell them apart will read silence as absence. Most of the
uncertainty handling below is that one principle:

* a fault verdict never reaches `anom-005`, so a fault bundle's track side
  is `NOT_APPLICABLE` **and says so** -- left absent it reads as
  not-measurable, which would claim an ignorance the system does not have;
* `not_measurable` corroboration -- 41 of 60 reported zones -- carries the
  *reason* rather than the flag, because a rate composed of nothing but
  `anom-012`'s smoothing constant is not a comparison of two observed rates;
* `not_corroborated` is **evidence**, not an uncertainty: it was measured
  and showed nothing, which is a finding;
* `anom-014`'s suppressed episodes are `MEASURED_NEGATIVE` -- looked at and
  too brief to call an event -- which is why that rule was given its own
  field rather than folding them in with the cells it could not judge.

**A superseded claim is never evidence.** A claim `anom-013` suppressed is
another rule's *competing* conclusion about the same place, so the likeliest
misreading is that co-occurrence is concurrence: a consumer handed both
writes that two independent rules flagged this area, which inverts the truth
exactly. Dropping it would make the bundle assert more confidence than the
system has, so it is carried in `superseded`, outside the evidence list. The
consequence for `ai-008` is recorded there: a grounding check that resolves
identifiers would certify a hypothesis citing one of these as support.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Sequence

from app.dal.models import DataMode, Location
from app.detection.findings import DetectionFinding
from app.detection.fusion import Corroboration, InterferenceZone
from app.detection.precedence import Claim, Resolution, Zone
from app.detection.rf_noise import RfNoiseFindings
from app.detection.sensor_fault import SensorFault
from app.detection.track_gap import RULE_ID as TRACK_RULE_ID
from app.scenario.layout import great_circle_km, load_layout

#: `anom-012` defines no rule id of its own -- it reads `anom-010`'s
#: findings and borrows that rule's identity. So a rate-excess item and a
#: discontinuity item carry the same rule id while making different claims,
#: and only `finding_type` separates them. Recorded rather than papered
#: over: it matters at `ai-008`, which resolves citations by rule id.
RATE_EXCESS_FINDING_TYPE = "track_rate_excess"


class BundleError(ValueError):
    """A bundle that cannot be built. Never a partial bundle."""


class Grounding(str, Enum):
    """What kind of claim an evidence item is making.

    The typed-absence principle this module already applies to
    uncertainties, applied to citations. 72 of 332 items in real bundles
    carry no refs at all -- a verdict, a nominal neighbour, a rate ratio --
    and those are judgements a rule made over readings, for which there is
    no row to cite. A nominal neighbour is in the bundle *precisely because*
    no episode was raised for it.

    Declaring it is what keeps "carries no refs" from being a state an item
    can drift into. `evb-002` checks every item, and the only way one
    escapes a database lookup is by saying it makes no observational claim
    -- so a new item type that forgets cannot acquire the weaker treatment
    by omission, because there is no default to acquire.
    """

    #: Cites raw observations. Every ref must resolve to exactly one row.
    OBSERVED = "observed"
    #: A judgement over readings, or over the other items in this bundle.
    #: Carries no refs at all, and carrying one is refused.
    DERIVED = "derived"


class UncertaintyKind(str, Enum):
    """The three things an absence can mean, kept apart on purpose."""

    #: Never consulted, by design. A fault verdict does not reach the
    #: fusion rule, so there is no track evidence *because none was sought*.
    NOT_APPLICABLE = "not_applicable"
    #: Consulted, and no basis on which to judge. A cell with no baseline;
    #: a rate over a reference period holding nothing.
    NOT_MEASURABLE = "not_measurable"
    #: Looked at, and found not to rise to a finding. `anom-014`'s episodes.
    MEASURED_NEGATIVE = "measured_negative"


@dataclass(frozen=True, slots=True)
class Uncertainty:
    """What the bundle does not know, and which *kind* of not-knowing."""

    kind: UncertaintyKind
    #: Written out, never the enum's own value. A consumer handed the bare
    #: word `not_measurable` learns nothing it can weigh.
    statement: str
    subject: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One observation or finding, with what produced it. FR-402."""

    source: str
    finding: str
    rule_id: str
    finding_type: str
    #: Per item and **not** per bundle: RF is ingested SYNTHETIC and
    #: replayed tracks REPLAYED, so a fusion bundle spans both by
    #: definition. One value on the bundle would have to be wrong, and the
    #: wrong one is the one telling an analyst which half is invented.
    data_mode: DataMode
    started_at: datetime
    ended_at: datetime
    #: No default, deliberately. See `Grounding`.
    grounding: Grounding
    refs: tuple[dict[str, Any], ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    #: Filled by `evb-002` at build time and never by this module: the rows
    #: each ref resolved to, in the order the refs were cited. Empty until
    #: the bundle has been resolved, and empty forever on a DERIVED item.
    observation_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        # Both directions, so the declaration cannot be a lie either way.
        if self.grounding is Grounding.OBSERVED and not self.refs:
            raise BundleError(
                f"evidence item {self.source!r} claims to be an observation and "
                "cites nothing. An item carrying no refs is skipped by the "
                "traceability check, so an item that merely *forgot* its refs "
                "would pass by default -- which is why the kind is declared."
            )
        if self.grounding is Grounding.DERIVED and self.refs:
            raise BundleError(
                f"evidence item {self.source!r} is declared a judgement and "
                f"cites {len(self.refs)} observation(s). A judgement has no row, "
                "so refs here mean the declaration is wrong in the direction "
                "that quietly exempts a real citation from being resolved."
            )

    def without_rule_id(self) -> EvidenceItem:
        """An item stripped of its rule id, for proving the bundle refuses it."""
        return replace(self, rule_id="")


@dataclass(frozen=True, slots=True)
class SupersededClaim:
    """A competing conclusion that was considered and did not win."""

    rule_id: str
    anomaly_type: str
    claimed_by: str
    reason: str


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """One account of one event. No ground truth, per `api-009`."""

    scenario_run_id: int
    anomaly_type: str
    rule_id: str
    subject: str
    time_window: tuple[datetime, datetime]
    affected_area: Location
    affected_channels: tuple[int, ...]
    evidence: tuple[EvidenceItem, ...]
    known_uncertainties: tuple[Uncertainty, ...]
    superseded: tuple[SupersededClaim, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence:
            raise BundleError(
                f"a bundle for {self.anomaly_type!r} on {self.subject!r} has no "
                "evidence. A bundle asserting an event with nothing behind it "
                "is what this object exists to prevent, and an empty one put in "
                "front of a model is worse than no bundle at all."
            )
        for item in self.evidence:
            if not item.rule_id:
                raise BundleError(
                    f"evidence item {item.source!r} carries no rule id. The rule "
                    "id is what makes an explanation checkable, so an item "
                    "without one is an assertion rather than evidence (FR-402), "
                    "and `ai-008` has nothing to resolve it against."
                )

    @property
    def data_modes(self) -> frozenset[DataMode]:
        """Every mode this bundle's evidence spans."""
        return frozenset(item.data_mode for item in self.evidence)

    def with_evidence(self, evidence: Sequence[EvidenceItem]) -> EvidenceBundle:
        """The same bundle over a different evidence list, re-validated."""
        return replace(self, evidence=tuple(evidence))


@lru_cache(maxsize=1)
def _zone_radius() -> float:
    """How near two claims count as one zone, from the layout.

    Read from `scn-005`'s layout rather than declared here, because
    `anom-013` reads it from exactly the same place. A constant repeated in
    two modules is a constant that will disagree with itself.
    """
    return load_layout().discrimination_radius_km


def build_bundles(
    resolution: Resolution,
    *,
    scenario_run_id: int,
    faults: Sequence[SensorFault] = (),
    zones: Sequence[InterferenceZone] = (),
    rf: RfNoiseFindings | None = None,
    track_findings: Sequence[DetectionFinding] = (),
    zone_radius_km: float | None = None,
) -> tuple[EvidenceBundle, ...]:
    """One bundle per reported claim, in the order the ladder reported them.

    A quiet run returns an empty tuple and **not** an empty bundle:
    `anom-008` requires zero reportable anomalies and this item
    independently requires an empty evidence list to fail the build, and the
    way those two agree is that nothing is created.

    `track_findings` are filtered here on the window only. Their spatial
    scoping is `anom-012`'s, which selected the disc through `db-004`, and
    measuring distance a second time in this module is the duplication the
    module docstring refuses.
    """
    findings = rf if rf is not None else RfNoiseFindings()
    radius = zone_radius_km if zone_radius_km is not None else _zone_radius()

    built: list[EvidenceBundle] = []
    for claim in resolution.reported:
        producer = _producer_for(claim, faults, zones)
        if isinstance(producer, SensorFault):
            bundle = _fault_bundle(claim, producer, findings, scenario_run_id)
        else:
            bundle = _zone_bundle(
                claim, producer, findings, track_findings, scenario_run_id)
        built.append(
            replace(bundle, superseded=_superseded_for(claim, resolution, radius)))
    return tuple(built)


def _zone_of(producer: SensorFault | InterferenceZone) -> Zone:
    centre = (producer.location if isinstance(producer, SensorFault)
              else producer.centre)
    return Zone(centre=centre, started_at=producer.started_at,
                ended_at=producer.ended_at)


def _producer_for(
    claim: Claim, faults: Sequence[SensorFault], zones: Sequence[InterferenceZone]
) -> SensorFault | InterferenceZone:
    """The rule output a reported claim was made from.

    Matched on rule id and the exact zone, because `claims_from_*` build a
    claim's zone from its producer's own centre and window -- so equality
    here is identity, not a proximity test dressed up as one.
    """
    candidates: tuple[SensorFault | InterferenceZone, ...] = (*faults, *zones)
    for producer in candidates:
        if producer.rule_id == claim.rule_id and _zone_of(producer) == claim.zone:
            return producer
    raise BundleError(
        f"no {claim.rule_id} output matches the reported claim at "
        f"{claim.zone.centre} over {claim.zone.started_at} to "
        f"{claim.zone.ended_at}. Building a bundle without the finding it "
        "describes would produce exactly the evidence-free bundle this item "
        "forbids, so this is refused rather than emitted thin."
    )


def _overlaps(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _episode_items(
    findings: RfNoiseFindings, sensors: Sequence[str],
    window: tuple[datetime, datetime]
) -> list[EvidenceItem]:
    """Every `anom-001` episode on these receivers during this window.

    **This is the frequency axis.** Episodes are raised per sensor per
    channel, so a wide event arrives as several, and collecting them under
    one bundle is what stops one event being handed over as eight.
    """
    items = []
    for episode in findings.anomalies:
        if episode.cell.sensor_id not in sensors:
            continue
        if not _overlaps((episode.started_at, episode.ended_at), window):
            continue
        items.append(EvidenceItem(
            source=f"{episode.cell.sensor_id}:{episode.cell.channel_index}",
            finding=(f"{episode.metric.value} deviated by "
                     f"{episode.peak_deviation:.2f} dB at its peak"),
            rule_id=episode.rule_id,
            finding_type=episode.anomaly_type,
            grounding=Grounding.OBSERVED,
            data_mode=DataMode.SYNTHETIC,
            started_at=episode.started_at,
            ended_at=episode.ended_at,
            refs=tuple({"sensor_id": ref.sensor_id,
                        "channel_index": ref.channel_index,
                        "timestamp": ref.timestamp.isoformat()}
                       for ref in episode.triggering),
            details={"metric": episode.metric.value,
                     "severity": episode.severity.value,
                     "peak_deviation": episode.peak_deviation},
        ))
    return items


def _rf_uncertainties(
    findings: RfNoiseFindings, sensors: Sequence[str]
) -> list[Uncertainty]:
    """Cells that could not be judged, and episodes too brief to be events."""
    out = []
    for cell in findings.unjudged:
        if cell.cell.sensor_id not in sensors:
            continue
        out.append(Uncertainty(
            kind=UncertaintyKind.NOT_MEASURABLE,
            subject=f"{cell.cell.sensor_id}:{cell.cell.channel_index}",
            statement=(f"channel {cell.cell.channel_index} of "
                       f"{cell.cell.sensor_id} was not judged: {cell.reason}. "
                       "This is a cell that was not looked at, not a cell "
                       "that was looked at and found quiet."),
        ))
    for brief in findings.suppressed:
        if brief.cell.sensor_id not in sensors:
            continue
        out.append(Uncertainty(
            kind=UncertaintyKind.MEASURED_NEGATIVE,
            subject=f"{brief.cell.sensor_id}:{brief.cell.channel_index}",
            statement=(f"a deviation on channel {brief.cell.channel_index} of "
                       f"{brief.cell.sensor_id} lasted {brief.readings} reading(s), "
                       f"under the {brief.minimum.total_seconds():.0f} s minimum, "
                       "so it was observed and not called an event."),
        ))
    return out


def _fault_bundle(
    claim: Claim, producer: SensorFault, findings: RfNoiseFindings, run_id: int
) -> EvidenceBundle:
    """A broken receiver, and the neighbours that prove it is the receiver."""
    window = (producer.started_at, producer.ended_at)
    sensors = (producer.sensor_id,)
    evidence = _episode_items(findings, sensors, window)

    spatial = producer.spatial
    elevations = dict(spatial.elevations)
    for neighbour in spatial.neighbours:
        if neighbour in spatial.abnormal or neighbour in spatial.unjudged:
            continue
        # A nominal neighbour is the *discriminating observation* -- the
        # reason this is a fault and not the environment -- so it is a
        # positive evidence item, never an absence.
        evidence.append(EvidenceItem(
            source=neighbour,
            finding=(f"{neighbour} was measured and stayed within "
                     f"{spatial.nominal_within_db:.1f} dB of its baseline"),
            rule_id=producer.rule_id,
            finding_type="neighbour_nominal",
            # A judgement, and an unusual one: this item exists precisely
            # because no episode was raised for this neighbour, so there is
            # nothing for it to cite by construction.
            grounding=Grounding.DERIVED,
            data_mode=DataMode.SYNTHETIC,
            started_at=producer.started_at,
            ended_at=producer.ended_at,
            details={"db": elevations.get(neighbour, 0.0),
                     "nominal_within_db": spatial.nominal_within_db,
                     "radius_km": spatial.radius_km},
        ))

    spectral = producer.spectral
    evidence.append(EvidenceItem(
        source=producer.sensor_id,
        finding=("the deviation is confined to "
                 f"{len(spectral.channels)} of {spectral.plan_size} channels"),
        rule_id=producer.rule_id,
        finding_type="channel_adjacency",
        grounding=Grounding.DERIVED,
        data_mode=DataMode.SYNTHETIC,
        started_at=producer.started_at,
        ended_at=producer.ended_at,
        details={"channels": list(spectral.channels),
                 "adjacent_checked": list(spectral.adjacent_checked),
                 "adjacent_abnormal": list(spectral.adjacent_abnormal)},
    ))
    evidence.append(EvidenceItem(
        source=producer.sensor_id,
        finding=("one receiver deviated while its measured neighbours stayed "
                 "nominal, which attributes the deviation to the instrument"),
        rule_id=producer.rule_id,
        finding_type=producer.anomaly_type,
        grounding=Grounding.DERIVED,
        data_mode=DataMode.SYNTHETIC,
        started_at=producer.started_at,
        ended_at=producer.ended_at,
        # Confidence qualifies the *attribution*, not the deviation, whose
        # severity `anom-001` already carries on its own items.
        details={"confidence": producer.confidence.value},
    ))

    uncertainties = [Uncertainty(
        kind=UncertaintyKind.NOT_APPLICABLE,
        subject="track",
        statement=("the aircraft side was not consulted. A single-receiver "
                   "fault verdict does not reach the fusion rule, so the "
                   "absence of track evidence here is by design and is not a "
                   "measurement that came back empty."),
    )]
    for neighbour in spatial.unjudged:
        uncertainties.append(Uncertainty(
            kind=UncertaintyKind.NOT_MEASURABLE,
            subject=neighbour,
            statement=(f"{neighbour} is inside the {spatial.radius_km:.0f} km "
                       "radius and could not be judged, so it is not evidence "
                       "either way."),
        ))
    for channel in spectral.adjacent_unjudged:
        uncertainties.append(Uncertainty(
            kind=UncertaintyKind.NOT_MEASURABLE,
            subject=f"{producer.sensor_id}:{channel}",
            statement=(f"adjacent channel {channel} could not be judged, so the "
                       "spectral test rests on the channels that could."),
        ))
    uncertainties.extend(_rf_uncertainties(findings, sensors))

    return EvidenceBundle(
        scenario_run_id=run_id,
        anomaly_type=producer.anomaly_type,
        rule_id=producer.rule_id,
        subject=producer.sensor_id,
        time_window=window,
        affected_area=producer.location,
        affected_channels=_channels(evidence, spectral.channels),
        evidence=tuple(evidence),
        known_uncertainties=tuple(uncertainties),
    )


def _zone_bundle(
    claim: Claim, producer: InterferenceZone, findings: RfNoiseFindings,
    track_findings: Sequence[DetectionFinding], run_id: int
) -> EvidenceBundle:
    """Interference, and whatever the aircraft side could contribute."""
    window = (producer.started_at, producer.ended_at)
    evidence = _episode_items(findings, producer.sensors, window)

    evidence.append(EvidenceItem(
        source=", ".join(producer.sensors),
        finding=producer.reason,
        rule_id=producer.rule_id,
        finding_type=producer.anomaly_type,
        grounding=Grounding.DERIVED,
        data_mode=DataMode.SYNTHETIC,
        started_at=producer.started_at,
        ended_at=producer.ended_at,
        details={"sensors": list(producer.sensors),
                 "confidence": producer.confidence.value,
                 "corroboration": producer.corroboration.value},
    ))

    uncertainties: list[Uncertainty] = []
    excess = producer.excess
    if excess is not None:
        # Measured, whichever way it came out. `not_corroborated` means the
        # rate WAS measured and showed nothing, which is a finding and
        # belongs here rather than among the things that are not known.
        evidence.append(EvidenceItem(
            source=f"{excess.radius_km:.0f} km disc",
            finding=(f"{excess.during} discontinuities during the window "
                     f"against {excess.outside} outside it, a rate ratio of "
                     f"{excess.ratio:.2f}"),
            rule_id=TRACK_RULE_ID,
            finding_type=RATE_EXCESS_FINDING_TYPE,
            # A ratio over counts. The discontinuities it counted are their
            # own OBSERVED items in this same bundle.
            grounding=Grounding.DERIVED,
            data_mode=DataMode.REPLAYED,
            started_at=excess.window[0],
            ended_at=excess.window[1],
            details={"during": excess.during, "outside": excess.outside,
                     "ratio": excess.ratio, "radius_km": excess.radius_km},
        ))
    if producer.corroboration is Corroboration.NOT_MEASURABLE:
        uncertainties.append(Uncertainty(
            kind=UncertaintyKind.NOT_MEASURABLE,
            subject="track",
            statement=("the local discontinuity rate could not be measured: the "
                       "reference period outside this window held no track "
                       "findings, so the ratio would consist of nothing but the "
                       "smoothing constant and is not a comparison of two "
                       "observed rates. This is the majority case, and it means "
                       "the aircraft side neither supports nor contradicts the "
                       "radio evidence here."),
        ))

    for finding in track_findings:
        if not _overlaps((finding.started_at, finding.ended_at), window):
            continue
        evidence.append(EvidenceItem(
            source=finding.subject,
            finding=("reporting from this aircraft broke during the window"),
            rule_id=finding.rule_id,
            finding_type=finding.finding_type,
            grounding=Grounding.OBSERVED,
            data_mode=DataMode.REPLAYED,
            started_at=finding.started_at,
            ended_at=finding.ended_at,
            refs=tuple(finding.evidence_refs),
            details=dict(finding.details),
        ))

    uncertainties.extend(_rf_uncertainties(findings, producer.sensors))

    return EvidenceBundle(
        scenario_run_id=run_id,
        anomaly_type=producer.anomaly_type,
        rule_id=producer.rule_id,
        subject=", ".join(producer.sensors),
        time_window=window,
        affected_area=producer.centre,
        affected_channels=_channels(evidence, ()),
        evidence=tuple(evidence),
        known_uncertainties=tuple(uncertainties),
    )


def _channels(
    evidence: Sequence[EvidenceItem], declared: Sequence[int]
) -> tuple[int, ...]:
    """Which channels this bundle actually carries evidence about.

    Taken from the items rather than from the rule's own summary, so the
    field describes the bundle instead of describing the rule that fed it.
    """
    seen = {ref["channel_index"] for item in evidence for ref in item.refs
            if "channel_index" in ref}
    return tuple(sorted(seen or set(declared)))


def _superseded_for(
    claim: Claim, resolution: Resolution, radius: float
) -> tuple[SupersededClaim, ...]:
    """The competing claims this claim took the zone from.

    Matched with `anom-013`'s own predicate -- the winning rule's id,
    window overlap, and the layout's discrimination radius -- rather than a
    second rule invented here. A suppression belongs to the zone it was
    suppressed in; attaching every run's suppressions to every bundle would
    put a competing explanation for somewhere else beside this event.
    """
    out = []
    for suppression in resolution.suppressed:
        if suppression.claimed_by != claim.rule_id:
            continue
        other = suppression.claim.zone
        if not claim.zone.overlaps(other):
            continue
        if great_circle_km(claim.zone.centre.lat, claim.zone.centre.lon,
                           other.centre.lat, other.centre.lon) > radius:
            continue
        out.append(SupersededClaim(
            rule_id=suppression.claim.rule_id,
            anomaly_type=suppression.claim.anomaly_type,
            claimed_by=suppression.claimed_by,
            reason=suppression.reason,
        ))
    return tuple(out)


__all__ = [
    "BundleError", "EvidenceBundle", "EvidenceItem", "Grounding", "SupersededClaim",
    "Uncertainty", "UncertaintyKind", "build_bundles",
]
