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

from datetime import UTC, datetime
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.schemas.scenario import (
    BatchInFlight,
    BatchRequest,
    ScenarioRunListing,
    ScenarioStartAccepted,
    ScenarioStartRequest,
)
from app.db.repository import list_runs
from app.db.session import SessionFactory, get_sessionmaker
from app.pipeline import derive_seeds
from app.scenario.batch import launch_batch
from app.scenario.guard import (
    BATCH_GUARD,
    BatchAlreadyRunning,
    BatchGuard,
    InFlightBatch,
    Lease,
)
from app.scenario.seeding import new_seed

router = APIRouter(prefix="/scenario", tags=["scenario"])


class BatchLauncher(Protocol):
    """Starts a batch and returns without waiting for it.

    Returning promptly is the contract, not an implementation detail: the route
    answers 202 immediately after calling this, so a launcher that blocked
    would silently turn the endpoint back into the seventy-second request the
    background thread exists to avoid.
    """

    def __call__(self, request: BatchRequest, lease: Lease) -> None: ...


def get_batch_launcher() -> BatchLauncher:
    """The seam. Overridden in tests by one that records instead of running."""
    return launch_batch


def get_batch_guard() -> BatchGuard:
    """The process's one guard (`api-011`), reached through the same seam.

    A dependency rather than a direct reference so the suite can substitute a
    fresh guard per test. What it must *not* be is the place the guard is
    **taken**: a dependency is resolved whether or not the request body
    validates, so a guard claimed here would be consumed by a 422 -- an unknown
    scenario type, a batch outside the run bounds, an incident beginning after
    its run ends -- and the next valid start would be refused 409 with nothing
    running at all.
    """
    return BATCH_GUARD


@router.post("/start", status_code=202)
def start_scenario(
    request: ScenarioStartRequest,
    launcher: BatchLauncher = Depends(get_batch_launcher),
    guard: BatchGuard = Depends(get_batch_guard),
) -> ScenarioStartAccepted:
    """Accept a batch and start it. spec: api-006.

    **202 rather than 200**, because the body is an acceptance rather than an
    outcome: the runs appear as rows over the following minute or so and the
    screen is already polling for them.

    The seed is drawn here when the caller omits one, never on the screen, and
    comes back in the response either way -- a run whose seed nobody was told
    cannot be reproduced from its record, which is the constraint this item has
    carried since it was written.

    **One batch at a time** (`api-011`). The guard is taken here, in the handler
    body, so a refused configuration cannot consume it; it is handed on to the
    launcher, because the release belongs to the thread that finishes the batch
    rather than to the call that starts it. A launcher that raises before its
    thread is running is the one case this frame has to clean up after: one
    failure leaving the guard held would disable the button until the container
    restarted, turning a recoverable error into an outage of the same kind this
    item exists to prevent.
    """
    base_seed = new_seed() if request.baseSeed is None else request.baseSeed
    seeds = derive_seeds(base_seed, request.runs)
    batch = request.resolved(base_seed)

    try:
        lease = guard.take(
            InFlightBatch(
                scenario_type=batch.scenario_type,
                base_seed=base_seed,
                started_at=datetime.now(UTC),
            )
        )
    except BatchAlreadyRunning as refusal:
        running = refusal.in_flight
        raise HTTPException(
            status_code=409,
            detail=BatchInFlight(
                scenarioType=running.scenario_type.value,
                baseSeed=running.base_seed,
                startedAt=running.started_at,
            ).model_dump(mode="json"),
        ) from refusal

    try:
        launcher(batch, lease)
    except Exception:
        lease.release()
        raise

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
