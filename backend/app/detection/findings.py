"""One shape every detection rule becomes. Spec: db-008.

The rules return different models. An RF episode carries a sensor-channel
cell, a severity and a peak deviation; a track discontinuity carries an
aircraft and which of two shapes it had. A storage layer that knew about
both would gain a branch per rule, and a third detector would mean editing
it -- which is exactly the dependency `dal-001` removed one layer down,
where every adapter's output becomes one canonical observation.

The same argument holds here, and it is the RQ1 extensibility claim made at
a second seam: **one shape every rule becomes**, with whatever is
rule-specific carried in `details`, so adding `anom-003` should need no
change to `app/db/findings.py` at all. That prediction is worth scoring
when it lands.

`evidence_refs` is already JSON: timestamps go in as ISO strings rather
than as `datetime`. A `datetime` nested in the payload would come back from
JSONB as a string, so a finding would not equal itself across a round trip
and every equality assertion about storage would be quietly false.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.dal.models import Location
from app.detection.rf_noise import RfNoiseAnomaly
from app.detection.track_gap import TrackGapFinding

if TYPE_CHECKING:
    # Under TYPE_CHECKING only: `app.detection.clustering` reaches the
    # database through `app.db.findings`, which imports this module, so a
    # runtime import here would close the loop. `app.detection.fusion` reaches
    # it the same way, through `app.detection.rate_excess`. `sensor_fault` does
    # not, and is here anyway: the two conclusions arrive together and a reader
    # should not have to work out which of them could be imported.
    from app.detection.clustering import TrackGapCluster
    from app.detection.fusion import InterferenceZone
    from app.detection.sensor_fault import SensorFault


@dataclass(frozen=True, slots=True)
class DetectionFinding:
    """What any rule's output looks like once it is ready to be stored."""

    scenario_run_id: int
    rule_id: str
    finding_type: str
    #: A sensor and channel for an RF episode, an aircraft for a track gap.
    subject: str
    started_at: datetime
    ended_at: datetime
    location: Location
    evidence_refs: tuple[dict[str, Any], ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


#: What makes two records of one reported claim the same claim.
#:
#: Rule, finding type, subject and window -- and **nothing derived**. Details
#: are rule-specific and a location is computed from them, so a claim whose
#: confidence moved under new settings would read as a different claim and the
#: comparison would report a disagreement that is not one.
ClaimIdentity = tuple[str, str, str, datetime, datetime]


def claim_identity(finding: DetectionFinding) -> ClaimIdentity:
    """One reported claim's identity, for comparing two records of it.

    **One derivation and never two.** `api-015` matches a stored bundle
    against the claim it explains, and `evb-003`'s fill compares a rebuilt
    claim against the stored one; those are the same question asked from two
    directions, and two spellings of it can disagree about which account
    belongs to which conclusion -- which is the ambiguity `api-015` refuses
    rather than resolves.

    It lives here and not in either caller because it is a property of
    `db-008`'s canonical finding. There is no key joining a bundle to its
    conclusion and there cannot be: findings are replaced per run per rule, so
    a foreign key would cascade-delete the bundles on every re-score, which is
    `db-011`'s argument one table along.
    """
    return (
        finding.rule_id,
        finding.finding_type,
        finding.subject,
        finding.started_at,
        finding.ended_at,
    )


@dataclass(frozen=True, slots=True)
class FindingCluster:
    """A group of findings that lie near one another. Spec: db-009.

    What turns a pile of intermediate findings into one object with a place
    and a size. A single track gap is not evidence -- a quiet run holds
    about 138 of them -- and a dozen inside a few kilometres of each other
    is; nothing in the system can say the second sentence without this.

    `hull_wkt` is the smallest convex shape covering the members, in the
    same WGS 84 the findings were stored in. It is a **point** for a group
    of one and a **line** for a group of two, not a polygon, and that is
    deliberate: a lone finding was observed at a point and has no extent,
    so inventing an area would claim ground nothing was seen across.
    Promoting a cluster to a reportable anomaly, whose affected area must
    be a polygon, is `anom-004`'s decision rather than this value's.
    """

    centroid: Location
    hull_wkt: str
    members: tuple[DetectionFinding, ...]

    @property
    def size(self) -> int:
        """How many findings chained together.

        One is the case `anom-006` cares about: a dropout that happened
        alone is a data-source problem rather than an incident.
        """
        return len(self.members)


def from_rf_noise(anomaly: RfNoiseAnomaly, *, scenario_run_id: int) -> DetectionFinding:
    """An `anom-001` episode as a storable finding.

    The severity travels in `details` rather than in a column of its own,
    because the track rule has none and `anom-008` made that deliberate.
    """
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=anomaly.rule_id,
        finding_type=anomaly.anomaly_type,
        subject=f"{anomaly.cell.sensor_id}:{anomaly.cell.channel_index}",
        started_at=anomaly.started_at,
        ended_at=anomaly.ended_at,
        location=anomaly.location,
        evidence_refs=tuple(
            {
                "sensor_id": ref.sensor_id,
                "channel_index": ref.channel_index,
                "timestamp": ref.timestamp.isoformat(),
            }
            for ref in anomaly.triggering
        ),
        details={
            "metric": anomaly.metric.value,
            "severity": anomaly.severity.value,
            "peak_deviation": anomaly.peak_deviation,
        },
    )


def from_track_gap(gap: TrackGapFinding, *, scenario_run_id: int) -> DetectionFinding:
    """An `anom-010` discontinuity as a storable finding.

    **The citation comes from `observed_at` and never from the window.**
    `evidence_refs` is a citation field and a citation must name a row; the
    window is what the rule *concluded*. For a not-heard gap the two agree,
    because its ends are the reports either side of the silence. For a
    frozen position they cannot: the window starts at the moment the
    position went stale, reconstructed by subtracting the staleness the
    report declares, and that is by definition the one instant in the window
    at which nothing was recorded. Writing the window here cost 91 of 1,021
    unresolvable citations in real bundles, every one of them that start,
    and it was invisible until `evb-002` looked the rows up (`qa.md` 83).
    """
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=gap.rule_id,
        finding_type=gap.finding_type,
        subject=gap.aircraft_id,
        started_at=gap.started_at,
        ended_at=gap.ended_at,
        location=gap.location,
        evidence_refs=(
            {"aircraft_id": gap.aircraft_id, "at": gap.observed_at[0].isoformat()},
            {"aircraft_id": gap.aircraft_id, "at": gap.observed_at[1].isoformat()},
        ),
        details={"shape": gap.shape.value, "duration_s": gap.duration.total_seconds()},
    )


def from_track_cluster(
    cluster: TrackGapCluster, *, scenario_run_id: int
) -> DetectionFinding:
    """An `anom-004` cluster as a storable finding.

    This is the first case that tests `db-008`'s claim properly. The shape
    was built from two rules whose finding is *about* one thing -- a
    sensor-channel cell, an aircraft -- and a cluster is about several. The
    claim was that a third detector needs no change to `app/db/findings.py`,
    and it holds: nothing in the storage layer knows this type exists.

    Where it strains is `subject`, which was described as "the thing
    observed" and here has to carry the things, plural, joined. Recording
    that as a partial rather than a clean score: the storage layer needed no
    edit, and one field's meaning had to widen to manage it. `anom-003` is
    still the prediction's fair test, since a z-score finding is about one
    cell again.

    No severity travels here, in `details` or anywhere else. A cluster is
    not reportable on its own -- measured -- and a severity written at this
    layer would be available to be read at the next.
    """
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=cluster.rule_id,
        finding_type=cluster.finding_type,
        subject=",".join(cluster.members),
        started_at=cluster.started_at,
        ended_at=cluster.ended_at,
        location=cluster.centroid,
        # Deliberately not a resolvable coordinate, and recorded as such:
        # an aircraft with no time matches every report it made rather than
        # one. `anom-004` clusters are not reportable, so no bundle cites
        # them, and `evb-002` refuses this shape by name rather than
        # matching it loosely -- which is the safer failure of the two.
        evidence_refs=tuple({"aircraft_id": aircraft} for aircraft in cluster.members),
        details={
            "size": cluster.size,
            "members": list(cluster.members),
            "hull_wkt": cluster.hull_wkt,
        },
    )


def from_sensor_fault(fault: SensorFault, *, scenario_run_id: int) -> DetectionFinding:
    """An `anom-007` attribution as a storable finding. Spec: anom-015.

    Added with `anom-015`'s second amendment, and the gap it closes is worth
    stating: the pass persisted its *evidence* and not its *conclusions*. The
    two rules at the end of the ladder returned their claims on the assessment
    and wrote nowhere, because the only reason the earlier rules were written
    down was that `anom-004` and `anom-012` read those rows back. Nothing reads
    a conclusion back inside one process -- and `api-012` is another process,
    where a conclusion nothing stored does not exist.

    **No refs, and the declaration is the point.** This rule measures no
    readings of its own: it judges the *shape* of an abnormality from
    `anom-001`'s episodes and the readings around them, so there is no row that
    is the fault. That is `evb-001`'s `Grounding.DERIVED` -- a judgement has no
    citation -- and writing the window here as a ref would be the defect
    `from_track_gap` records, one rule along.

    **The confidence travels in `details` and qualifies the attribution**, never
    the deviation, whose severity `anom-001` already carries on its own rows.
    The neighbour evidence travels with it because the attribution is only
    checkable against what was asked: "every receiver within 70 km read nominal"
    is the claim, and a row carrying the verdict without the receivers states a
    conclusion an analyst cannot test.
    """
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=fault.rule_id,
        finding_type=fault.anomaly_type,
        subject=fault.sensor_id,
        started_at=fault.started_at,
        ended_at=fault.ended_at,
        location=fault.location,
        details={
            "confidence": fault.confidence.value,
            "neighbours": list(fault.spatial.neighbours),
            "neighbour_radius_km": fault.spatial.radius_km,
            "channels": list(fault.spectral.channels),
        },
    )


def from_interference_zone(
    zone: InterferenceZone, *, scenario_run_id: int
) -> DetectionFinding:
    """An `anom-005` zone as a storable finding. Spec: anom-015.

    **The subject names one receiver and `details` names them all**, which is
    not redundancy. `anom-005`'s zone is established by more than one receiver
    deviating together and its window is the **union** of theirs, so a row
    keeping only the subject misreports which receivers the claim rests on --
    and `anom-009` computes this rule's latency from a count of receivers
    precisely because the union's start is the first one's and not the claim's.
    `from_track_cluster` joined its subjects into one field and recorded the
    strain; here the subject stays one receiver and the set goes in `details`,
    because a reader of this row needs to know which receiver it is *filed*
    under as well as which ones it spans.

    `corroboration` is carried as its own value and not folded into the
    confidence: it is three-valued, and the third value is the common one -- 47
    of 61 zones on the real corpus could not be measured at all, because a
    period holding no findings has a rate consisting of nothing but the
    smoothing constant. Collapsed to a boolean, *measured and below threshold*
    and *not measurable* become one answer, which is the distinction `anom-012`
    exists to keep.

    No refs, for `from_sensor_fault`'s reason: this rule consumes another rule's
    verdict and measures nothing itself.
    """
    return DetectionFinding(
        scenario_run_id=scenario_run_id,
        rule_id=zone.rule_id,
        finding_type=zone.anomaly_type,
        subject=zone.sensors[0],
        started_at=zone.started_at,
        ended_at=zone.ended_at,
        location=zone.centre,
        details={
            "confidence": zone.confidence.value,
            "sensors": list(zone.sensors),
            "corroboration": zone.corroboration.value,
        },
    )
