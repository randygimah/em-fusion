"""System health route. Spec: api-001, ops-005.

It answers **without** a database and reports **on** one when there is one, and
the distinction is the whole of `ops-005`. `api-001`'s rule is that this route
must not *require* a connection to answer -- so that it stays truthful before
persistence exists and so a degraded database does not present as an unreachable
service. That rule was read for a year as "touch nothing", which is why nothing
noticed when `api-012`'s migration was applied to the test database and never to
the application's: `/api/v1/operational-picture` returned 500 for a day while
this route answered 200 and the container reported itself healthy.

So the route now consults the database when it can and refuses only when the
schema has **drifted**. A database that cannot be reached answers 200 and says it
could not tell, which keeps `api-001`'s guarantee intact and is the reason this
is not a startup check: `db-005` opens no connection at startup on purpose.

The factory is annotated through `app.db.session`'s own alias rather than by
naming `sqlalchemy.orm`, which `db-006` forbids in a route module and which the
purity check caught on the first draft of this file.

**503 and not a 200 carrying a sad field**, because the thing that was silent is
the container probe -- it runs `urlopen` against this path, and only a non-2xx
makes the container report unhealthy. A body nobody parses is what we already had.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.db.repository import schema_state
from app.db.session import (
    EngineNotInitialisedError,
    SessionFactory,
    get_sessionmaker,
)

router = APIRouter()


def get_sessions() -> SessionFactory | None:
    """The process's session factory, or None before one exists.

    A dependency rather than a direct call, following `api-006`'s pattern, so a
    test can point this route at a real database without standing up an Engine
    for the whole process. `None` rather than a raise, because `api-001` requires
    this route to answer before persistence exists and the lifespan is what builds
    the Engine.
    """
    try:
        return get_sessionmaker()
    except EngineNotInitialisedError:
        return None


@router.get("/health", tags=["system"])
def get_health(
    sessions: SessionFactory | None = Depends(get_sessions),
) -> JSONResponse:
    """Report that the service is up, and whether its schema is current."""
    state = schema_state(sessions)
    return JSONResponse(
        status_code=200 if state.healthy else 503,
        content={
            "status": "healthy" if state.healthy else "unhealthy",
            "schema": state.status,
            "expected": state.expected,
            "found": state.found,
            "detail": state.detail,
        },
    )
