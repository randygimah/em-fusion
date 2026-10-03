"""Operational picture route. Spec: api-002.

The one endpoint the dashboard reads. It holds no SQL, no session
construction and no spatial logic: `FR-904` puts all three in the repository,
and `db-006` is the test that says so once this route exists to assert against.
What is left here is the shape of the request -- which run, and how much of it.

**Separate calls, not one.** The run is chosen first and everything else read
for it afterwards, because "which run" is a policy question (`db-007`: prefer
one known to have finished) and the rest are queries. A single joined read
would work and would bury the policy inside SQL, where the reason for it cannot
be stated.

**Four reads for one payload, and the fourth is the item.** Spec: `api-012`.
Positions, findings, and whether a detection pass examined this run at all --
that last one cannot be inferred from the findings, because `db-008` replaces
them per run per rule *including at zero*, so a run examined and found clean
leaves exactly what a run nobody examined leaves. `anom-015` stamps the run,
and this reads the stamp.

**The layout is loaded, not queried.** `scn-005`'s receivers are configuration
the generator reads too, so they are served whether or not a pass has run; what
the pass governs is each receiver's *health*, which is `unknown` without one. On
every request rather than at import: `load_layout` fails loudly on a malformed
file, and a module-level read would turn that into an import error at startup
with no route to report it through.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.schemas.operational_picture import (
    OperationalPicture,
    SelectableHour,
    build_operational_picture,
)
from app.db.findings import findings_for_run
from app.db.repository import detection_pass_for_run, latest_positions, latest_run
from app.db.session import SessionFactory, get_sessionmaker
from app.scenario.layout import load_layout

router = APIRouter()

#: How far back from the end of a run its "current" picture reaches. Matches
#: the replay's own batch length, so a picture covers the last thing written
#: rather than a fraction of it or several batches of it.
FINAL_WINDOW_SECONDS = 300


@router.get("/operational-picture", tags=["operational-picture"])
def get_operational_picture(
    sessions: SessionFactory = Depends(get_sessionmaker),
) -> OperationalPicture:
    """The current picture, or an empty one. spec: api-002.

    An empty database is a 200 with a null scenario rather than a 404 or a
    500: before the first run there is nothing to serve, and a screen that
    cannot render until someone has run a replay is a screen nobody can
    develop against (`op-001` requires it to render with scenario data absent).
    """
    run = latest_run(sessions)
    if run is None:
        return build_operational_picture(
            run=None, observations=[], layout=load_layout()
        )
    return build_operational_picture(
        run=run,
        observations=latest_positions(sessions, run.id, FINAL_WINDOW_SECONDS),
        layout=load_layout(),
        findings=findings_for_run(sessions, run.id),
        detection_pass=detection_pass_for_run(sessions, run.id),
    )


@router.get("/operational-picture/hours", tags=["operational-picture"])
def get_selectable_hours(
    sessions: SessionFactory = Depends(get_sessionmaker),
) -> list[SelectableHour]:
    """STUB -- api-013 not implemented."""
    raise NotImplementedError("api-013")
