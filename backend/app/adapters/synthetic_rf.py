"""The synthetic RF source, driven into the store. Spec: adp-002.

The counterpart of `opensky.py`, and deliberately the same shape: one module
per source, taking its repository and pseudonymiser rather than constructing
either, so the adapter/DAL seam looks the same from both sides and a third
adapter has one pattern to copy rather than two to choose between.

**A driver, and nothing else.** Every number in the stream comes from
`scn-001`'s emitter, which stays in `app/scenario/`. Nothing here derives a
reading, and the structural tests assert that by absence -- an adapter that
invented a value of its own would sit outside everything `scn-001` proves about
determinism, and the run record would describe a stream nobody could reproduce.

**The unit of work is one run, not one window.** `adp-007` tiles a replay into
five-minute batches because a replay that lost twelve committed batches would
have to re-read the corpus to get them back. A synthetic run has no such cost:
it regenerates byte-identically from its seed, so all-or-nothing at run scale is
free to retry, and it is what `scn-003` needs -- a run that wrote half its grid
before failing would be skipped by the batch and still counted as evidence by
whatever read the table afterwards. One run at the shipped layout is 5,040
records over fifteen minutes, comparable to one of `adp-007`'s twelve batches,
so the large-transaction objection that shaped the replay does not arise here.

**The incident is planned here, not supplied.** The caller passes a `RunSpec`
and gets the staging that spec implies. Accepting an `Incident` instead would
let a caller emit a quiet grid under a run row claiming interference -- the
answer key and the observations disagreeing, with nothing to catch it, on the
one record the evaluation is scored against. `plan_incident` is a pure function
of the layout and the spec, so `scn-003` planning it again for the ground truth
gets the same answer by construction.

**The data mode is not an argument.** `SYNTHETIC` is the only mode a synthetic
source may claim, and `op-001`'s badge reads that field off the data rather than
off a UI constant, so a mislabelled row makes the interface lie about what the
analyst is looking at. Building the context here rather than accepting one
removes the argument a caller could get wrong.

**The pseudonymiser is carried and unused.** `IDENTIFIER_RULES` has no entry for
RF, so `substitute` is a no-op on these payloads. It is passed anyway rather
than made optional at the DAL: a single ingest entrypoint with a bypass for one
source is no longer the guarantee `dal-002` and `dal-003` rest on, and the next
source would arrive to find two ways in.

**It creates no run.** The `scenario_run_id` arrives from whoever opened the
run -- `scn-003`'s batch -- and recording ground truth and marking completion
belong there too. Every producer of a run sets those (`db-007`), and an adapter
that quietly created its own parent row would be a second definition of what a
run is.
"""

from __future__ import annotations

from app.dal.ingest import IngestResult, ingest_batch
from app.dal.models import DataMode
from app.dal.pseudonymise import Pseudonymiser
from app.dal.repository import ObservationRepository
from app.dal.validation import IngestContext
from app.scenario.emitter import RunSpec, emit_rf
from app.scenario.incident import plan_incident
from app.scenario.layout import RfLayout


def emit_run(
    layout: RfLayout,
    spec: RunSpec,
    scenario_run_id: int,
    repository: ObservationRepository,
    pseudonymiser: Pseudonymiser,
) -> IngestResult:
    """Emit one run's grid and drive it through the DAL. Returns the counts.

    Raises whatever the repository raises. A failed write is reported rather
    than swallowed, because `scn-003` can only record and skip a run that told
    it something went wrong -- and a driver that returned counts over a write
    that never happened would report a full grid stored and leave nothing
    behind.
    """
    return ingest_batch(
        emit_rf(layout, spec, plan_incident(layout, spec)),
        IngestContext(data_mode=DataMode.SYNTHETIC, scenario_run_id=scenario_run_id),
        repository,
        pseudonymiser,
    )
