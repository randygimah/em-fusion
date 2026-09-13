"""Scenario control routes. Spec: api-006.

Two endpoints, not three. `POST /scenario/reset` is deferred to its own item
and its control stays disabled on screen: a run is a row, `db-007` records that
nothing is ever deleted, and "a cleared run state" has no honest meaning until
a batch can be in flight and abandoned. Inventing a destructive endpoint to
fill the name, or a no-op one that returns 200 and changes nothing, are both
worse than a control that says plainly it is not wired.

Neither handler holds SQL, builds a session or wires a batch (`FR-904`). The
launcher is injected, which is what lets the refusals be tested as *nothing was
started* without a corpus on disk or a database to start it against.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Depends

from app.api.v1.schemas.scenario import (
    BatchRequest,
    ScenarioRunListing,
    ScenarioStartAccepted,
    ScenarioStartRequest,
)
from app.db.repository import list_runs
from app.db.session import SessionFactory, get_sessionmaker
from app.pipeline import derive_seeds
from app.scenario.batch import launch_batch
from app.scenario.seeding import new_seed

router = APIRouter(prefix="/scenario", tags=["scenario"])


class BatchLauncher(Protocol):
    """Starts a batch and returns without waiting for it.

    Returning promptly is the contract, not an implementation detail: the route
    answers 202 immediately after calling this, so a launcher that blocked
    would silently turn the endpoint back into the seventy-second request the
    background thread exists to avoid.
    """

    def __call__(self, request: BatchRequest) -> None: ...


def get_batch_launcher() -> BatchLauncher:
    """The seam. Overridden in tests by one that records instead of running."""
    return launch_batch


@router.post("/start", status_code=202)
def start_scenario(
    request: ScenarioStartRequest,
    launcher: BatchLauncher = Depends(get_batch_launcher),
) -> ScenarioStartAccepted:
    """Accept a batch and start it. spec: api-006.

    **202 rather than 200**, because the body is an acceptance rather than an
    outcome: the runs appear as rows over the following minute or so and the
    screen is already polling for them.

    The seed is drawn here when the caller omits one, never on the screen, and
    comes back in the response either way -- a run whose seed nobody was told
    cannot be reproduced from its record, which is the constraint this item has
    carried since it was written.
    """
    base_seed = new_seed() if request.baseSeed is None else request.baseSeed
    seeds = derive_seeds(base_seed, request.runs)

    launcher(request.resolved(base_seed))

    return ScenarioStartAccepted(
        baseSeed=base_seed, runs=request.runs, seeds=list(seeds)
    )


@router.get("/runs")
def get_scenario_runs(
    sessions: SessionFactory = Depends(get_sessionmaker),
) -> list[ScenarioRunListing]:
    """Recent runs, newest first. spec: api-006.

    An empty database is a 200 with an empty list rather than a 404, for
    `api-002`'s reason: a screen that cannot render until somebody has run a
    batch is a screen nobody can develop against.
    """
    return [
        ScenarioRunListing(
            id=run.id,
            scenarioType=run.scenario_type,
            seed=run.seed,
            startedAt=run.started_at,
            completedAt=run.completed_at,
            parameters=run.parameters,
        )
        for run in list_runs(sessions)
    ]
