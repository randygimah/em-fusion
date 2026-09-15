"""Where detection findings are written and read. Spec: db-008.

All the SQL for `detection_findings`, and the only module above the
detectors that knows the table exists -- FR-904's rule about where SQL
lives, applied to the new table as it is to `observations`.

**The write replaces rather than appends**, per run per rule. Detection is
deterministic and regenerable from the run's seed, so a finding is derived
rather than historical, and `db-007`'s rule that nothing is ever deleted
does not reach it: that rule is about runs, which are facts about what
happened. Appending would be the worse failure -- after a rule changes, the
old findings would sit beside the new and every metric in `eval-002` would
count both, with nothing on screen or in a log to say so.

Writing an *empty* set of findings therefore clears what was there. A rule
that found nothing this time must not leave last time's findings standing;
it is the same argument at zero.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session, sessionmaker

from app.dal.models import Location
from app.detection.findings import DetectionFinding

#: WGS 84, the SRID every geometry column in `db-001` declares.
SRID = 4326


def _ewkt(location: Location) -> str:
    """A point as EWKT text, longitude first.

    Longitude is X and latitude is Y, and the two are the same kind of
    number, so a transposition produces valid geometry in the wrong place
    and no error anywhere. Written as one function so there is exactly one
    place the order is decided.

    Text rather than GeoAlchemy2's `WKTElement`, which is what
    `app/db/repository.py` uses: that module builds its statements from a
    reflected table whose column carries the geometry type, and the type is
    what adapts the element. These statements are textual, so the driver
    sees a bare parameter and cannot adapt it -- the insert therefore hands
    PostGIS the EWKT and lets `ST_GeomFromEWKT` parse it, which keeps the
    SRID attached to the value rather than assumed by the column.
    """
    return f"SRID={SRID};POINT({location.lon} {location.lat})"


def save_findings(
    session_factory: sessionmaker[Session],
    *,
    scenario_run_id: int,
    rule_id: str,
    findings: Iterable[DetectionFinding],
) -> None:
    """Replace this rule's findings for this run.

    One transaction, so a failed write leaves the previous set intact rather
    than deleting it and then failing to insert -- which would report an
    error and silently leave the run with no findings at all.
    """
    rows = [_row(finding) for finding in findings]

    with session_factory.begin() as session:
        session.execute(
            text(
                "DELETE FROM detection_findings "
                "WHERE scenario_run_id = :run_id AND rule_id = :rule_id"
            ),
            {"run_id": scenario_run_id, "rule_id": rule_id},
        )
        if rows:
            session.execute(
                text(
                    "INSERT INTO detection_findings "
                    "(scenario_run_id, rule_id, finding_type, subject, "
                    " started_at, ended_at, evidence_refs, details, location) "
                    "VALUES (:scenario_run_id, :rule_id, :finding_type, :subject, "
                    " :started_at, :ended_at, :evidence_refs, :details, "
                    " ST_GeomFromEWKT(:location))"
                ),
                rows,
            )


def findings_for_run(
    session_factory: sessionmaker[Session],
    run_id: int,
    *,
    rule_id: str | None = None,
) -> list[DetectionFinding]:
    """Everything found on one run, oldest first.

    An empty result is an empty list. A run with no findings is an ordinary
    outcome -- `anom-008` requires it of every quiet run -- not an error and
    not a null for the caller to remember to test.
    """
    clause = "" if rule_id is None else " AND rule_id = :rule_id"
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    "SELECT scenario_run_id, rule_id, finding_type, subject, "
                    "  started_at, ended_at, evidence_refs, details, "
                    "  ST_Y(location) AS lat, ST_X(location) AS lon "
                    "FROM detection_findings "
                    f"WHERE scenario_run_id = :run_id{clause} "
                    "ORDER BY started_at, subject, id"
                ),
                {"run_id": run_id, "rule_id": rule_id},
            )
            .mappings()
            .all()
        )
    return [_finding(row) for row in rows]


def _row(finding: DetectionFinding) -> dict[str, object]:
    """One finding as the insert's parameters.

    The two JSON payloads are serialised here rather than passed as dicts,
    because the statement is textual and psycopg would otherwise adapt a
    plain dict to a PostgreSQL composite type rather than to JSONB.
    """
    return {
        "scenario_run_id": finding.scenario_run_id,
        "rule_id": finding.rule_id,
        "finding_type": finding.finding_type,
        "subject": finding.subject,
        "started_at": finding.started_at,
        "ended_at": finding.ended_at,
        "evidence_refs": json.dumps(list(finding.evidence_refs)),
        "details": json.dumps(finding.details),
        "location": _ewkt(finding.location),
    }


def _finding(row: RowMapping) -> DetectionFinding:
    """One row back into the model it was written from."""
    refs: Sequence[dict[str, object]] = row["evidence_refs"]
    return DetectionFinding(
        scenario_run_id=row["scenario_run_id"],
        rule_id=row["rule_id"],
        finding_type=row["finding_type"],
        subject=row["subject"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        location=Location(lat=row["lat"], lon=row["lon"]),
        evidence_refs=tuple(refs),
        details=row["details"],
    )


def findings_near(
    session_factory: sessionmaker[Session],
    *,
    scenario_run_id: int,
    centre: Location,
    radius_km: float,
    window: tuple[datetime, datetime],
    rule_id: str | None = None,
) -> list[DetectionFinding]:
    """Findings within `radius_km` of a point, overlapping a window. Spec: db-004.

    FR-905's one real spatial query, and the justification for running a
    spatial database rather than storing two float columns.

    **Distance is measured on geography, in metres.** The stored geometry is
    in degrees (SRID 4326), and a degree is not a distance: at 52 degrees
    north a degree of longitude is about 69 km while a degree of latitude is
    about 111, so a radius applied to raw coordinates is wrong by a different
    factor in each direction and wrong by a different amount at each latitude.
    The cast is what makes the number mean kilometres.

    **The window test is overlap, not containment.** A finding is itself an
    interval, and `anom-005` fuses an RF deviation with a track gap occurring
    in the same window -- a gap that began before the window opened is still
    happening during it. Requiring containment would drop exactly the long
    disruptions the fusion rule exists to find. `OVERLAPS` is PostgreSQL's
    own operator for this rather than four hand-written comparisons.

    **The bounding-box prefilter is what lets the index help.** `&&` tests
    the geometry index; `ST_DWithin` on geography then measures exactly. The
    expansion is generous on purpose -- a degree of longitude is shortest at
    the highest latitude the corpus box reaches, so dividing by the cosine
    there over-covers everywhere else, and an over-wide prefilter costs a few
    extra exact comparisons while an under-wide one silently loses rows.
    """
    if radius_km <= 0:
        raise ValueError(f"radius_km={radius_km} must be positive")

    clause = "" if rule_id is None else " AND rule_id = :rule_id"
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    "SELECT scenario_run_id, rule_id, finding_type, subject, "
                    "  started_at, ended_at, evidence_refs, details, "
                    "  ST_Y(location) AS lat, ST_X(location) AS lon "
                    "FROM detection_findings "
                    "WHERE scenario_run_id = :run_id"
                    f"{clause} "
                    "  AND (started_at, ended_at) OVERLAPS (:window_start, :window_end) "
                    "  AND location && ST_Expand("
                    "        ST_GeomFromEWKT(:centre), :expand_deg) "
                    "  AND ST_DWithin(location::geography, "
                    "        ST_GeomFromEWKT(:centre)::geography, :metres)"
                    "ORDER BY started_at, subject, id"
                ),
                {
                    "run_id": scenario_run_id,
                    "rule_id": rule_id,
                    "window_start": window[0],
                    "window_end": window[1],
                    "centre": _ewkt(centre),
                    "expand_deg": _expansion_degrees(radius_km),
                    "metres": radius_km * 1000.0,
                },
            )
            .mappings()
            .all()
        )
    return [_finding(row) for row in rows]


#: The corpus box reaches 54 degrees north, where a degree of longitude is at
#: its shortest across the box. Expanding by the radius divided by that
#: length over-covers at every lower latitude, which is the safe direction:
#: the prefilter only has to be a superset of the answer.
_KM_PER_DEGREE_AT_BOX_TOP = 65.4


def _expansion_degrees(radius_km: float) -> float:
    """How far in degrees to widen the bounding box for the index prefilter."""
    return radius_km / _KM_PER_DEGREE_AT_BOX_TOP
