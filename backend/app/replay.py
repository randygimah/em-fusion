"""Replay entrypoint: the archived corpus into the database. Spec: adp-007.

The operator surface over machinery that already exists. `adp-001` reads
windows, the DAL validates and pseudonymises, `db-003` writes; this module
parses arguments, wires the three together, and reports what happened. It
holds no reading logic and no SQL of its own beyond the one run row it
creates, because anything it invented here would be a second implementation
of something already tested elsewhere.

**It fails before it writes.** The seed is read, the manifest parsed and the
span checked before an Engine is built, so a misconfigured invocation leaves
no orphan `scenario_runs` row behind. `main` returns an exit code and never
raises for an expected failure -- a command that reports success on failure
cannot be used in a script or in CI.

**The unit of work is one window, not one run.** `dal-002`'s all-or-nothing
guarantee therefore holds per batch: an interrupted replay leaves the windows
already written in place. A single transaction spanning the hour was
rejected as a 133,634-row write held open for the length of the replay. This
is a deliberate weakening, it is stated in `adp-007`, and a test asserts it so
that quietly strengthening it later fails rather than passes.

**It loads `.env`, and `app/main.py` does not.** Following `app.corpus.build`
rather than the server: both are operator CLIs run by hand, whereas the server
is run through Compose, which supplies the environment itself
(`docs/qa.md` section 37).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import TextIO

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import text

from app.adapters.opensky import Window, available_window, replay_window
from app.dal.models import DataMode
from app.dal.pseudonymise import SEED_ENV_VAR, Pseudonymiser
from app.dal.repository import ObservationRepository
from app.dal.validation import IngestContext
from app.db.repository import PostgisObservationRepository, complete_scenario_run
from app.db.session import dispose_engine, get_sessionmaker, init_engine

#: Repository root, two levels up from `backend/app/`. Correct natively; in
#: the container it resolves to `/`, because Compose mounts `./backend` as
#: `/app` and the repository above it does not exist there. `make replay`
#: therefore mounts the data directory and passes `--data-dir` explicitly
#: rather than relying on this default.
REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATA_DIR = REPO_ROOT / "data" / "opensky"

#: Anchored to the package rather than to the repository, so it resolves in
#: both places: `backend/.env` natively and `/app/.env` in the container, which
#: is the same file through the bind mount. `app/corpus/build.py` anchors its
#: own copy to the repository root and gets away with it only because it is
#: never run in a container.
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

#: Five minutes of simulated time per batch. Small enough that an interrupted
#: replay loses little, large enough that the per-batch overhead is not what
#: the wall-time figure ends up measuring.
DEFAULT_WINDOW_SECONDS = 300

EXTRACT_NAME = "opensky_extract.parquet"
MANIFEST_NAME = "manifest.json"

#: The scenario type a replay-created run carries. A replay injects nothing,
#: so it is not one of the five scenario types -- but `observations` has a NOT
#: NULL foreign key to `scenario_runs` and no generator exists yet, so a run
#: has to come from somewhere. Written with a type nothing else uses, so
#: `scn-001` can find these rows rather than have to infer them.
REPLAY_SCENARIO_TYPE = "replay-only"


class ReplaySummary(BaseModel):
    """What one replay did.

    The balance rule is enforced on the model rather than checked at the call
    site. `dal-002` requires that nothing is silently dropped, and at this
    level that guarantee reduces to arithmetic: every row read left as either
    an observation or a quarantine record. A summary that fails it cannot be
    constructed, so it cannot be printed or copied into a thesis table either.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rows_read: int
    accepted: int
    quarantined: int
    batches: int
    seconds: float

    @model_validator(mode="after")
    def _counts_balance(self) -> ReplaySummary:
        if self.rows_read != self.accepted + self.quarantined:
            raise ValueError(
                f"{self.rows_read} rows read but {self.accepted} accepted and "
                f"{self.quarantined} quarantined: nothing may be silently "
                "dropped (dal-002)."
            )
        return self

    def render(self) -> str:
        return (
            f"rows read:    {self.rows_read}\n"
            f"accepted:     {self.accepted}\n"
            f"quarantined:  {self.quarantined}\n"
            f"batches:      {self.batches}\n"
            f"seconds:      {self.seconds:.2f}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.replay",
        description=(
            "Replay the archived OpenSky extract through the Data Abstraction "
            "Layer into the database."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"directory holding {MANIFEST_NAME} (default: %(default)s)",
    )
    parser.add_argument(
        "--window-seconds",
        type=int,
        default=DEFAULT_WINDOW_SECONDS,
        help=(
            "simulated seconds per batch, and therefore per transaction "
            "(default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--start",
        type=datetime.fromisoformat,
        help="ISO timestamp to replay from (default: the start of the corpus)",
    )
    parser.add_argument(
        "--end",
        type=datetime.fromisoformat,
        help="ISO timestamp to replay to, exclusive (default: the corpus end)",
    )
    return parser


def windows(span: Window, seconds: int) -> list[Window]:
    """Tile a span into consecutive windows of at most `seconds`.

    `Window` is half-open, so consecutive tiles meet exactly once: an overlap
    would duplicate a frame, which reads downstream as a zero-second
    inter-sample gap, and a hole would manufacture a dropout indistinguishable
    from the one scenario type 4 injects. The final tile is truncated to the
    span rather than rounded up, so a replay never asks for frames beyond the
    span it was given.
    """
    if seconds <= 0:
        raise ValueError(
            f"window length must be positive, got {seconds}: zero would tile "
            "forever and a negative value would tile backwards."
        )

    step = timedelta(seconds=seconds)
    tiles: list[Window] = []
    start = span.start
    while start < span.end:
        tiles.append(Window(start=start, end=min(start + step, span.end)))
        start += step
    return tiles


def create_scenario_run() -> int:
    """Insert the placeholder run this replay's observations belong to.

    The only SQL in this module, and it is here rather than in the repository
    because it is `scn-001`'s row being borrowed rather than the repository's
    to own. `ground_truth` is null: a replay injects nothing, and `api-009`
    requires it never leave the run record in any case.
    """
    with get_sessionmaker().begin() as session:
        return int(
            session.execute(
                text(
                    "INSERT INTO scenario_runs "
                    "(scenario_type, parameters, seed, started_at) "
                    "VALUES (:kind, '{}'::jsonb, 0, now()) RETURNING id"
                ),
                {"kind": REPLAY_SCENARIO_TYPE},
            ).scalar_one()
        )


def replay(
    *,
    path: Path,
    spans: Sequence[Window],
    scenario_run_id: int,
    repository: ObservationRepository,
    pseudonymiser: Pseudonymiser,
) -> ReplaySummary:
    """Drive every window through the DAL and report the totals.

    The repository and pseudonymiser are supplied rather than constructed, for
    the same reason `adp-001` requires it one level down: building either here
    would couple this module to a storage engine and to process configuration,
    and would make the interrupted-run test impossible to write.
    """
    context = IngestContext(
        data_mode=DataMode.REPLAYED, scenario_run_id=scenario_run_id
    )
    accepted = quarantined = 0
    started = perf_counter()

    for span in spans:
        result = replay_window(path, span, context, repository, pseudonymiser)
        accepted += result.accepted
        quarantined += result.quarantined

    return ReplaySummary(
        rows_read=accepted + quarantined,
        accepted=accepted,
        quarantined=quarantined,
        batches=len(spans),
        seconds=perf_counter() - started,
    )


def _requested_span(
    corpus: Window, start: datetime | None, end: datetime | None
) -> Window:
    """The span to replay, clipped to what the corpus actually covers.

    An empty result is an error rather than a quiet success: a run that writes
    nothing and exits zero is the shape of a silent failure, and the whole
    point of this command is producing a figure someone will quote.
    """
    span = Window(start=start or corpus.start, end=end or corpus.end)
    clipped = Window(start=max(span.start, corpus.start), end=min(span.end, corpus.end))
    if clipped.start >= clipped.end:
        raise ValueError(
            f"requested span {span.start.isoformat()} to {span.end.isoformat()} "
            f"does not overlap the corpus span {corpus.start.isoformat()} to "
            f"{corpus.end.isoformat()}."
        )
    return clipped


def main(
    argv: Sequence[str] | None = None,
    *,
    env_file: Path | None = DEFAULT_ENV_FILE,
    stdout: TextIO | None = None,
) -> int:
    """Run the replay. Returns a process exit code; never raises for an
    expected failure."""
    out = stdout if stdout is not None else sys.stdout
    args = build_parser().parse_args(argv)

    # Compose passes the seed through from the host, so an *unset* host
    # variable arrives inside the container as an empty string rather than as
    # absent -- and `load_dotenv(override=False)` treats present-but-empty as
    # present, which would let nothing shadow a perfectly good `.env`. An empty
    # seed is not a seed, which `Pseudonymiser.from_environment` already says
    # one layer down, so it is cleared before the file is read.
    if not os.environ.get(SEED_ENV_VAR, "").strip():
        os.environ.pop(SEED_ENV_VAR, None)

    if env_file is not None and Path(env_file).is_file():
        load_dotenv(env_file, override=False)

    data_dir = Path(args.data_dir)

    # Everything below this point that can fail without a database, does --
    # before `init_engine`, so a bad invocation cannot leave an orphan run.
    try:
        pseudonymiser = Pseudonymiser.from_environment()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    manifest_path = data_dir / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(f"cannot read {manifest_path}: {error}", file=sys.stderr)
        return 2

    extract = data_dir / EXTRACT_NAME
    if not extract.is_file():
        print(
            f"cannot read {extract}: the corpus is gitignored and is rebuilt "
            f"from the manifest by `python -m app.corpus.build`.",
            file=sys.stderr,
        )
        return 2

    try:
        span = _requested_span(available_window(manifest), args.start, args.end)
        spans = windows(span, args.window_seconds)
    except (KeyError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    init_engine()
    try:
        repository = PostgisObservationRepository(get_sessionmaker())
        scenario_run_id = create_scenario_run()
        summary = replay(
            path=extract,
            spans=spans,
            scenario_run_id=scenario_run_id,
            repository=repository,
            pseudonymiser=pseudonymiser,
        )
        # `db-007`, and deliberately the last statement in the try block. The
        # run is marked after every batch has committed, so a replay that dies
        # part-way leaves the flag null -- which is the only state a killed
        # process can be trusted to leave behind.
        complete_scenario_run(get_sessionmaker(), scenario_run_id)
    except Exception as error:  # noqa: BLE001 -- reported, not swallowed
        print(f"replay failed: {error}", file=sys.stderr)
        return 1
    finally:
        dispose_engine()

    print(summary.render(), file=out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
