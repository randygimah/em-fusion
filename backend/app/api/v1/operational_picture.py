"""Operational picture route. Spec: api-002.

The one endpoint the dashboard reads. It holds no SQL, no session
construction and no spatial logic: `FR-904` puts all three in the repository,
and `db-006` is the test that says so once this route exists to assert against.
What is left here is the shape of the request -- which run, and how much of it.

**Two calls, not one.** The run is chosen first and the positions read for it
second, because "which run" is a policy question (`db-007`: prefer one known to
have finished) and "which positions" is a query. A single joined read would
work and would bury the policy inside SQL, where the reason for it cannot be
stated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.schemas.operational_picture import (
    OperationalPicture,
    build_operational_picture,
)
from app.db.repository import latest_positions, latest_run
from app.db.session import SessionFactory, get_sessionmaker

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
    observations = (
        [] if run is None else latest_positions(sessions, run.id, FINAL_WINDOW_SECONDS)
    )
    return build_operational_picture(run=run, observations=observations)
