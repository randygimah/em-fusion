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

**It also scores what it generated** (`anom-016`), and the placement is the whole
of that decision. `app/pipeline.py`'s `main()` calls `run_batch` directly, so
`python -m app.pipeline` -- the Compose `pipeline` service and `make generate` --
generates and does not score; the scoring sits in `run_batch_now`, which only the
screen's path reaches. Two code paths that differ is normally a smell and here it
is the point: the 300 hours behind every figure this project quotes were built by
that command, and a command that scored them would stamp them with whatever
settings happened to be current, after which the same hours could never be
re-scored under a different threshold (`eval-001`). Unscored **by construction**
rather than by a parameter somebody must remember not to pass.

Scoring inside `run_batch_now` also puts it inside `api-011`'s lease, which is not
incidental: the pass opens its own sessions against the one Engine (`db-003`), and
that is exactly the pool exhaustion the guard was written for -- measured over
generation only. Outside the lease it would reintroduce the observed cause in the
one place nothing has measured.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING

from app.adapters.opensky import available_window
from app.dal.pseudonymise import Pseudonymiser, load_seed_environment
from app.db.repository import PostgisObservationRepository, run_summary
from app.db.session import get_sessionmaker
from app.detection.chain import (
    DetectorPolicies,
    PinnedRun,
    assess,
    measure_normality,
)
from app.detection.settings import (
    BASELINE_QUIET_RUNS,
    BASELINE_WINDOW,
    POLICIES_OF_RECORD,
)
from app.pipeline import EXCLUSIONS_NAME, BatchSummary, run_batch
from app.replay import DEFAULT_DATA_DIR, DEFAULT_ENV_FILE, EXTRACT_NAME, MANIFEST_NAME
from app.scenario.guard import Lease
from app.scenario.layout import RfLayout, load_layout
from app.scenario.tracks import load_exclusions

# Under TYPE_CHECKING because it is only ever an annotation, and importing it for
# real is a cycle: anything under `app.api.v1` runs that package's `__init__`,
# which imports the route module, which imports this one. It had never fired
# because nothing imported this module before the API package -- which `anom-016`
# does, needing `score_batch` without standing up a FastAPI app.
if TYPE_CHECKING:
    from app.api.v1.schemas.scenario import BatchRequest

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
    layout = load_layout()
    summary = run_batch(
        layout,
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
    # `anom-016`. After generation and never inside it, so the corpus and the
    # detector settings stay separable; and before the lease is released, which
    # happens in `launch_batch`'s `finally`.
    scoring = score_batch(summary, session_factory=sessions, layout=layout)
    logger.info("scenario batch scored: %s", scoring.describe())


@dataclass(frozen=True, slots=True)
class BatchScoring:
    """What the detection pass made of one batch. Spec: anom-016.

    A report rather than nothing, because every failure here is **recorded and
    stepped over** and a caller that learns nothing cannot say which. `refused`
    is the whole-batch case -- no baseline to measure normal against, which since
    `anom-017` includes a store that does not hold the pinned quiet runs -- and is
    separate from a per-run failure for the same reason `anom-006`'s absent rule
    is separate from `anom-004`'s unpersisted one: collapsed together, a store
    problem reads as a detector problem.
    """

    #: The batch's completed runs: the only runs this examines.
    requested: tuple[int, ...]
    scored: tuple[int, ...]
    failed: tuple[tuple[int, str], ...]
    #: Why nothing was examined at all, or None. A batch with nothing to examine
    #: is not a refusal: there is no store problem there.
    refused: str | None

    def describe(self) -> str:
        if self.refused is not None:
            return f"refused over {len(self.requested)} runs: {self.refused}"
        return (
            f"{len(self.scored)} of {len(self.requested)} runs examined, "
            f"{len(self.failed)} failed"
        )


def score_batch(
    summary: BatchSummary,
    *,
    session_factory: object,
    layout: RfLayout,
    policies: DetectorPolicies = POLICIES_OF_RECORD,
    window: timedelta = BASELINE_WINDOW,
    quiet_runs: Sequence[PinnedRun] = BASELINE_QUIET_RUNS,
) -> BatchScoring:
    """Run the detection pass over the runs this batch produced. Spec: anom-016.

    **Only this batch's completed runs**, never the store. Three hundred runs is
    about six minutes, and it would rewrite every figure-of-record run's findings
    under whatever settings are current -- the coupling `eval-001` moved off
    itself. The batch's own `completed` flag filters here and `anom-015` refuses
    an unfinished run anyway from the stamp on its row, so this is the cheap check
    rather than the only one.

    **One baseline for the whole batch.** It costs 11.2 s against 1.22 s a run, so
    one per run would turn a twenty-run batch's 35 s into nearly four minutes --
    and two baselines inside one batch would make two of its runs incomparable.

    **Nothing raises out of here.** Anything escaping reaches `launch_batch`,
    which logs *scenario batch failed* -- a false statement, the batch having
    generated and stored every hour it was asked for. So the catch is broad on
    purpose: a `ChainError` is a refusal the pass decided on, anything else is a
    defect, and both leave the run unstamped, which is exactly what it is. The
    screen needs no new channel for that: `api-012` serves an unstamped run a null
    detection summary and says in words that nothing has examined it.

    **The settings are the record's** unless a caller is deliberately re-scoring.
    The parameter is what makes the same hours re-readable under another
    threshold; the default is what makes a figure on the screen the same figure as
    a figure in the thesis. The quiet runs are one of those settings since
    `anom-017`: pinned by default, and a refusal when the store does not hold them.
    """
    requested = tuple(
        outcome.run_id
        for outcome in summary.runs
        if outcome.completed and outcome.run_id is not None
    )
    if not requested:
        return BatchScoring(requested=(), scored=(), failed=(), refused=None)

    try:
        normality = measure_normality(
            session_factory,
            # `anom-017`: the pinned population, never the store's quiet runs of
            # the moment -- those made the baseline vary with the store's size.
            quiet_runs=quiet_runs,
            policies=policies,
            window=window,
        )
    except Exception as exc:
        logger.warning("detection pass refused over %s runs: %s", len(requested), exc)
        return BatchScoring(requested=requested, scored=(), failed=(), refused=str(exc))

    scored: list[int] = []
    failed: list[tuple[int, str]] = []
    for run_id in requested:
        try:
            run = run_summary(session_factory, run_id)  # type: ignore[arg-type]
            if run is None:
                raise LookupError(f"run {run_id} is not in the store")
            assess(
                run,
                normality=normality,
                policies=policies,
                layout=layout,
                session_factory=session_factory,
            )
        except Exception as exc:
            logger.exception("detection pass failed on run %s", run_id)
            failed.append((run_id, str(exc)))
        else:
            scored.append(run_id)

    return BatchScoring(
        requested=requested,
        scored=tuple(scored),
        failed=tuple(failed),
        refused=None,
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
