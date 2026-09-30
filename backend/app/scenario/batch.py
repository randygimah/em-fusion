"""Running a batch without making the caller wait for it. Spec: api-006.

A batch is roughly seventy seconds and half a million rows, and the project has
no task queue by scope. This module is the whole of that decision: the request
returns at once and the work happens on a thread.

**Why not block.** Seventy seconds against an nginx whose default
`proxy_read_timeout` is sixty would pass in development and 504 in the
container -- the exact shape of defect this project keeps recording.

**Why not a queued row.** Nothing would drain it until a worker exists, which
is out of scope, so the screen would grow a button that changes a row and
produces no run. That is worse than the disabled button it replaces, which at
least says why it does nothing.

**What it costs.** Nothing can cancel a started batch, and a process killed
mid-batch leaves runs with a null `completed_at`. That second one is not a new
state to invent: `db-007` already defines absence as *not known to have
finished*, and everything that reads runs already ignores those. The first is
why `POST /scenario/reset` is deferred to its own item rather than dropped --
reset only means something once there is an in-flight batch to abandon.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Thread

from app.adapters.opensky import available_window
from app.api.v1.schemas.scenario import BatchRequest
from app.dal.pseudonymise import Pseudonymiser, load_seed_environment
from app.db.repository import PostgisObservationRepository
from app.db.session import get_sessionmaker
from app.pipeline import EXCLUSIONS_NAME, run_batch
from app.replay import DEFAULT_DATA_DIR, DEFAULT_ENV_FILE, EXTRACT_NAME, MANIFEST_NAME
from app.scenario.guard import Lease
from app.scenario.layout import load_layout
from app.scenario.tracks import load_exclusions

logger = logging.getLogger(__name__)


def run_batch_now(
    request: BatchRequest,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    env_file: Path | None = DEFAULT_ENV_FILE,
) -> None:
    """Run one batch to completion, on whatever thread calls this.

    It borrows the API's own engine through `get_sessionmaker` rather than
    calling `init_engine`: there is one Engine per process (`db-003`), built by
    the application's lifespan, and a batch that built a second one would
    dispose the first out from under every in-flight request.
    """
    # Before anything else. The seed arrives from compose present-but-empty
    # when the host has not exported it, and every batch started from the
    # screen died on that until this call existed.
    load_seed_environment(env_file)

    manifest = json.loads((data_dir / MANIFEST_NAME).read_text())
    sessions = get_sessionmaker()
    run_batch(
        load_layout(),
        scenario_type=request.scenario_type,
        base_seed=request.base_seed,
        count=request.runs,
        corpus=available_window(manifest),
        duration_seconds=request.duration_seconds,
        extract=data_dir / EXTRACT_NAME,
        repository=PostgisObservationRepository(sessions),
        pseudonymiser=Pseudonymiser.from_environment(),
        session_factory=sessions,
        incident=request.incident,
        excluded=load_exclusions(data_dir / EXCLUSIONS_NAME),
    )


def launch_batch(request: BatchRequest, lease: Lease) -> None:
    """Start a batch and return immediately. The launcher the route uses.

    Failures are logged and go no further. There is nobody left to raise to --
    the response was sent before this thread was scheduled -- and the run rows
    already written are the record of what happened, which is the same posture
    `run_batch` takes toward a single run that fails inside a batch.

    **The lease is released in the thread's `finally`, always** (`api-011`).
    Here and not where this function returns: it returns within microseconds and
    the batch runs for about seventy seconds, so a release at the call site would
    free the guard before a single run row had been opened. And in a `finally`
    rather than after the call, because a batch that raises must free it too --
    one failure leaving the guard held would disable the button until the
    container restarted, which is a worse defect than the one the guard fixes.
    """

    def work() -> None:
        try:
            run_batch_now(request)
        except Exception:
            logger.exception(
                "scenario batch failed: type=%s base_seed=%s runs=%s",
                request.scenario_type.value,
                request.base_seed,
                request.runs,
            )
        finally:
            lease.release()

    Thread(target=work, name="scenario-batch", daemon=True).start()
