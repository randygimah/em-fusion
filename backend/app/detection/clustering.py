"""Spatial clustering of track discontinuities, rule ID `TRACK-CLUSTER`.
Spec: anom-004.

A thin rule over `db-009`, and thin deliberately: the query does the
grouping and this adds the rule's identity, its radius, and a refusal.

**Cluster size is never on its own reportable, and that is a measurement
rather than a preference.** Over eight seed-matched triples from the stored
batch, the largest cluster a staged run produces is *identical* to the
largest cluster in its own matched control in all eight, at every radius
from 5 to 20 km; at 30 to 60 km the difference is 0.12 to 0.25 clusters.
Findings per run are 15.9 on staged runs against 16.0 on controls. The
control is an `rf-sensor-fault` run at the same seed rather than a
`normal-baseline` one, because no baseline run in the batch shares a seed
with a staged run and so replays different traffic, while `rf-sensor-fault`
shares seeds and perturbs nothing on the track side.

So clustering track gaps cannot tell a staged run from a quiet one, and a
rule reporting on cluster size would be reporting background. `anom-011`
carries the reason and the remedy: `TRACK-GAP` recall is 21 per cent, so
the signal is the same size as the noise it would have to be separated
from. Every rule above this one is gated on that item.

**The radius is not fitted.** The measurement covers 5 to 60 km and
separates staged runs from their controls at none of it, so no value here
was chosen because it worked. The default is the radius of a staged
incident zone, which is the scale the thing being looked for actually has,
and the measurement is recorded beside it so a later reader cannot mistake
it for a tuned parameter.

**A cluster of one is kept.** This item originally said an isolated
discontinuity forms no cluster, which contradicts `db-009` and would delete
what `anom-006` reads: a source that goes quiet by itself, with nothing
near it, is an infrastructure problem rather than an incident. What a
cluster of one *means* is the consuming rule's decision, not this one's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.dal.models import Location
from app.db.findings import cluster_findings
from app.detection.track_gap import RULE_ID as SOURCE_RULE_ID

RULE_ID = "TRACK-CLUSTER"

#: Intermediate, and named so it cannot be mistaken for otherwise. The
#: reportable types all begin `possible_`, because they are what an analyst
#: is shown and what `anom-008`'s control counts.
FINDING_TYPE = "track_gap_cluster"

#: The radius of a staged incident zone -- the scale of the thing being
#: looked for, not a value chosen because it separated anything. See the
#: module docstring.
DEFAULT_RADIUS_KM = 60.0


@dataclass(frozen=True, slots=True)
class ClusterPolicy:
    """How close two discontinuities must be to belong to one disruption."""

    radius_km: float = DEFAULT_RADIUS_KM

    def __post_init__(self) -> None:
        # Refused here rather than at the query, so a nonsensical radius
        # cannot reach the database at all. An empty result would otherwise
        # be indistinguishable from nothing clustering.
        if self.radius_km <= 0:
            raise ValueError(f"radius_km={self.radius_km} must be positive")


@dataclass(frozen=True, slots=True)
class TrackGapCluster:
    """Discontinuities that happened near each other.

    **No severity, and no confidence or score either.** `anom-001` gives
    its episodes a severity because they are shown to an analyst; this is
    not shown to anyone. A severity field here would be a number with
    nothing behind it, and the way to keep it out is to have nowhere to put
    it -- the same structural argument `anom-010` makes one layer down,
    asserted by a test that reads the dataclass's fields.
    """

    centroid: Location
    hull_wkt: str
    started_at: datetime
    ended_at: datetime
    #: The aircraft, in the order `db-009` returns them: by time, then by
    #: aircraft, then by row. Never the order rows came back from storage.
    members: tuple[str, ...]
    finding_type: str = FINDING_TYPE
    rule_id: str = RULE_ID

    @property
    def size(self) -> int:
        """How many discontinuities chained together.

        One is the case `anom-006` cares about and the reason singletons
        are not discarded.
        """
        return len(self.members)


def cluster_track_gaps(
    session_factory: sessionmaker[Session],
    *,
    scenario_run_id: int,
    window: tuple[datetime, datetime],
    policy: ClusterPolicy,
) -> tuple[TrackGapCluster, ...]:
    """Group one run's track discontinuities by where they happened.

    Only `TRACK-GAP` findings. An RF episode sits at a receiver and a track
    gap at an aircraft, so grouping the two by distance would fuse them by
    accident -- and fusing them deliberately is `anom-005`'s job, through
    the proximity query rather than this one.

    A run with no discontinuities gives an empty tuple. That is the
    ordinary outcome `anom-008` requires of a quiet run, not an error.
    """
    grouped = cluster_findings(
        session_factory,
        scenario_run_id=scenario_run_id,
        rule_id=SOURCE_RULE_ID,
        radius_km=policy.radius_km,
        window=window,
    )

    return tuple(
        TrackGapCluster(
            centroid=cluster.centroid,
            hull_wkt=cluster.hull_wkt,
            # The union of the members' windows, not the first member's: a
            # cluster is the disruption, and the disruption lasted as long
            # as its longest part.
            started_at=min(member.started_at for member in cluster.members),
            ended_at=max(member.ended_at for member in cluster.members),
            members=tuple(member.subject for member in cluster.members),
        )
        for cluster in grouped
    )
