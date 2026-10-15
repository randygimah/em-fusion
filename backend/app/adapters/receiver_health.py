"""The receiver health feed, driven into the store. Spec: adp-003.

`synthetic_rf.py`'s shape, copied: a driver that takes its repository and
pseudonymiser, fixes the data mode, derives nothing and creates no run. The
numbers are `app/scenario/receiver_health.py`'s.

It takes the seed and window rather than a `RunSpec`, so nothing about what a
run stages passes through it (`api-009`). Not wired into the batch or the
pipeline: it runs in tests only.
"""

from __future__ import annotations

from datetime import datetime

from app.dal.ingest import IngestResult, ingest_batch
from app.dal.models import DataMode
from app.dal.pseudonymise import Pseudonymiser
from app.dal.repository import ObservationRepository
from app.dal.validation import IngestContext
from app.scenario.layout import RfLayout
from app.scenario.receiver_health import emit_health


def emit_run(
    layout: RfLayout,
    *,
    seed: int,
    start: datetime,
    duration_seconds: int,
    scenario_run_id: int,
    repository: ObservationRepository,
    pseudonymiser: Pseudonymiser,
) -> IngestResult:
    """Emit one run's feed and drive it through the DAL. Returns the counts;
    raises whatever the repository raises."""
    return ingest_batch(
        emit_health(layout, seed, start, duration_seconds),
        IngestContext(data_mode=DataMode.SYNTHETIC, scenario_run_id=scenario_run_id),
        repository,
        pseudonymiser,
    )
