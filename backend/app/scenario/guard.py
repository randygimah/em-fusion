"""One batch at a time. Spec: api-011.

The backend was found hung on ``QueuePool limit of size 5 overflow 10 reached,
connection timed out`` -- not slow, unserviceable, with its container reporting
unhealthy -- after several batches had been started from the screen in quick
succession. Measured afterwards, one batch is harmless: it adds a single
connection while ``/health`` stays 200 throughout. So the fault is concurrency
rather than batches. Every start spawns another unbounded daemon thread
(`api-006`) and every thread borrows the API's one engine (`db-003`), so batches
compete with request serving for a pool whose ceiling is SQLAlchemy's default
fifteen. Bounding the count at one removes the observed cause. It does not make
the pool safe against arbitrary load, and nothing here claims that.

**Nothing is written to the database, and that is `db-007`'s own argument rather
than laziness.** A batch cannot outlive the process running it, so a persisted
*running* flag would be a claim no crash could retract: kill the container
mid-batch and the row still says a batch is in flight, locking the button until
somebody edits the database. `db-007` rejected exactly this when it refused a
three-valued status column, on the grounds that a process killed outright cannot
record its own death. In-memory state has the property that argument wanted -- a
restart genuinely means nothing is in flight, and the state says so by not
existing.

**Sound only while the API is one process.** Uvicorn is started with no
``--workers`` in the Dockerfile's two stages and in the Compose command that
overrides them, so there is one worker today; adding workers would give each its
own guard and silently restore the defect. The guard and the condition it depends
on are therefore asserted together in the suite, because the guard alone would
keep passing while becoming untrue.

**A lease rather than a flag, because the release belongs to the thread.** The
launcher returns within microseconds and the batch it started runs for about
seventy seconds, so releasing where the launcher returns would free the guard
before the batch had opened a single run row -- which is not a weaker guard but
the absence of one. What the route takes is a lease, and the lease travels across
the launcher seam so the thread's own ``finally`` can hand it back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from app.scenario.incident import ScenarioType


@dataclass(frozen=True, slots=True)
class InFlightBatch:
    """What is running, in the words a refusal is allowed to use.

    Three fields and no fourth. An analyst who cannot tell *which* batch is in
    flight, or how long it has been, cannot tell whether to wait or to
    investigate -- and the information costs nothing, the guard holding it in
    order to exist. What was *staged* is not here, per `api-009`: no window, no
    sensors, no aircraft, no incident.

    `started_at` is the **wall clock**, deliberately, and this is the one place
    in the project where that is the right answer. `anom-009` exists because
    detection latency would otherwise have reached for a wall-clock timestamp
    wearing a simulated-time costume, and the rule that came out of it is that a
    time about the simulated world is taken from the simulated world. This time
    is not about the simulated world: it answers how long a real process on a
    real machine has been running.
    """

    scenario_type: ScenarioType
    base_seed: int
    started_at: datetime


class BatchAlreadyRunning(Exception):
    """Raised by `BatchGuard.take` when a batch is already in flight.

    It carries the running batch rather than merely saying *no*, and carrying it
    is why this is an exception instead of a falsy return: the two facts have to
    arrive together. A caller told only *no*, left to ask what is running
    afterwards, races the batch it is asking about -- that batch can finish in
    between, leaving a 409 with nothing to name.
    """

    def __init__(self, in_flight: InFlightBatch) -> None:
        super().__init__(
            f"a {in_flight.scenario_type.value} batch from base seed "
            f"{in_flight.base_seed} has been running since {in_flight.started_at}"
        )
        self.in_flight = in_flight


class Lease:
    """The right to run one batch, and the obligation to give it back.

    Constructed only by the guard. `release` is safe to call more than once and
    safe to call late, and the mechanism matters: it clears the guard only while
    *this* lease is still the holder. A release that simply cleared it would let
    a lease from a finished batch free the guard a later batch is holding, and
    then two batches run at once -- the item defeated by the very mechanism meant
    to enforce it.
    """

    def __init__(self, guard: BatchGuard, in_flight: InFlightBatch) -> None:
        self._guard = guard
        self.in_flight = in_flight

    def release(self) -> None:
        self._guard._release(self)


class BatchGuard:
    """Admits one batch at a time, for this process, for as long as it lives.

    `take` is atomic. A check followed by a set lets two simultaneous callers
    both observe *nothing running* and both proceed, which defeats the item
    entirely while passing any test that takes the guard twice in a row.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._held: Lease | None = None

    def take(self, in_flight: InFlightBatch) -> Lease:
        """Claim the right to run this batch, or refuse naming the holder."""
        with self._lock:
            if self._held is not None:
                raise BatchAlreadyRunning(self._held.in_flight)
            self._held = Lease(self, in_flight)
            return self._held

    @property
    def in_flight(self) -> InFlightBatch | None:
        """The batch running now, or `None` -- which is the whole state."""
        with self._lock:
            return None if self._held is None else self._held.in_flight

    def _release(self, lease: Lease) -> None:
        with self._lock:
            if self._held is lease:
                self._held = None


#: The process's one guard. A module-level singleton is exactly the scope the
#: second decision argues for: per process, gone on restart, never written down.
#: The route reaches it through a dependency so the suite can substitute a fresh
#: one per test -- a guard shared between tests would refuse the second test's
#: batch on account of the first test's.
BATCH_GUARD = BatchGuard()
