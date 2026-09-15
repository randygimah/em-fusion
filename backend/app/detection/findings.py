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
    # runtime import here would close the loop.
    from app.detection.clustering import TrackGapCluster


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

    The window ends are the evidence: for a gap measured as an absence they
    are the reports either side of it, which is what `anom-010` was asked to
    carry and what an analyst would look up.
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
            {"aircraft_id": gap.aircraft_id, "at": gap.started_at.isoformat()},
            {"aircraft_id": gap.aircraft_id, "at": gap.ended_at.isoformat()},
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
        evidence_refs=tuple({"aircraft_id": aircraft} for aircraft in cluster.members),
        details={
            "size": cluster.size,
            "members": list(cluster.members),
            "hull_wkt": cluster.hull_wkt,
        },
    )
