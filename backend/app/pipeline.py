"""Batch execution: many runs from one number. Spec: scn-003 (pass 1 of 2).

`scn-001` made one run reproducible from one seed. This makes a campaign
reproducible from one seed, which is a different claim and needs two things the
single run never did: every run must get its own seed, and every run must get
its own stretch of the recorded hour.

**Seeds are derived, not drawn.** The same argument `seeding.py` makes about
readings applies a level up. A sequence advanced once per run makes run 19's
seed a function of how many runs preceded it, so a batch of thirty and a batch
of twenty disagree about what run 19 was, and asking for five more runs
tomorrow renumbers the campaign. Keyed derivation makes run *i* a function of
the base and *i*, so `derive_seeds(base, 30)[:20] == derive_seeds(base, 20)`
holds by construction and a batch can be extended without being invalidated.

**Distinctness is guaranteed rather than assumed.** Two runs sharing a seed is
one of this item's failure cases, and the seed space is wide enough that it
would never be seen in testing and would eventually happen in a campaign. The
window space is not wide enough even for that comfort: a fifteen-minute run
inside a one-hour corpus leaves 2,701 whole-second places to stand, and
twenty-five draws collide about one time in eight -- measured 2026-09-12 across
five base seeds, two of which produced a repeat. Both derivations therefore
re-derive under a new key when a value repeats, which keeps the result a pure
function of the base while removing the collision entirely.

**Why windows vary at all.** The incident's zone centre comes from the run's
seed and the layout has seven receivers, so a batch of twenty to thirty runs
stages at the same place several times over -- measured, every receiver is used,
two to six times each. Runs sharing a centre *and* a window would be
near-duplicates: the same aircraft, in the same place, differing only in the
invented noise. The corpus still bounds how independent they can be, since
thirty fifteen-minute windows inside one hour overlap heavily; that is recorded
as a limitation of the evaluation rather than papered over here.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import TextIO, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.opensky import Window, available_window, replay_window
from app.adapters.synthetic_rf import emit_run
from app.dal.models import DataMode
from app.dal.pseudonymise import Pseudonymiser, load_seed_environment
from app.dal.repository import ObservationRepository
from app.dal.validation import IngestContext
from app.db.repository import (
    PostgisObservationRepository,
    complete_scenario_run,
    create_scenario_run,
    record_ground_truth,
)
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.replay import (
    DEFAULT_DATA_DIR,
    DEFAULT_ENV_FILE,
    EXTRACT_NAME,
    MANIFEST_NAME,
)
from app.scenario.emitter import BaselineParameters, RunSpec
from app.scenario.incident import (
    IncidentParameters,
    ScenarioType,
    SpectralExtent,
    ground_truth,
    plan_incident,
)
from app.scenario.layout import RfLayout, load_layout
from app.scenario.seeding import SEED_MAX, derive_unit
from app.scenario.tracks import TrackPerturber, load_exclusions, plan_track_perturbation

#: The run count a batch must fall within (`scn-003`, FR-205). A campaign
#: smaller than this cannot carry a per-type rate worth quoting; larger is not
#: forbidden by anything except the cost of scoring it by hand.
MIN_RUNS = 20
MAX_RUNS = 30

#: Fifteen minutes of simulated time per run. Long enough to hold an incident
#: with quiet ticks either side of it, short enough that thirty of them fit
#: inside the recorded hour at thirty different offsets.
DEFAULT_RUN_SECONDS = 900

#: The exclusion list `adp-008` builds beside the corpus: tracks carrying a
#: natural interior airborne gap, which a staged gap must never land on.
EXCLUSIONS_NAME = "natural_gaps.json"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


#: How many times a repeated value may be re-derived before the derivation
#: itself is declared broken. A keyed derivation finds a free value in one or
#: two attempts and a thousand is unreachable by chance. It exists for the
#: unreachable-by-chance case: a derivation that has stopped keying on its
#: retry counter returns the same value forever, and without a bound the loop
#: below spins rather than failing -- a campaign that hangs instead of
#: reporting. Found by mutating the window offset to a constant, which did
#: exactly that.
_MAX_ATTEMPTS = 1000

_T = TypeVar("_T")


def _distinct(value_of: Callable[[int, int], _T], count: int) -> tuple[_T, ...]:
    """`count` values from a keyed derivation, with repeats re-derived.

    The retry key is part of the derivation rather than a post-hoc fix-up, so
    the result is still determined entirely by whatever the caller keyed on.
    Value *i* depends on values 0 to *i-1* only through which of them were
    taken, so a prefix of a longer batch is still the shorter batch -- the
    property that lets a campaign be extended rather than regenerated.
    """
    seen: set[_T] = set()
    values: list[_T] = []
    for index in range(count):
        attempt = 0
        value = value_of(index, attempt)
        while value in seen:
            attempt += 1
            if attempt >= _MAX_ATTEMPTS:
                raise RuntimeError(
                    f"value {index} repeated on every one of {_MAX_ATTEMPTS} "
                    "attempts: the derivation is no longer keyed on its retry "
                    "counter, so re-deriving cannot resolve a collision."
                )
            value = value_of(index, attempt)
        seen.add(value)
        values.append(value)
    return tuple(values)


def derive_seeds(base_seed: int, count: int) -> tuple[int, ...]:
    """The seeds of a batch, all distinct, all reproducible from `base_seed`.

    Bounded by the width of `scenario_runs.seed` for the reason `new_seed` is:
    a seed that does not round-trip through the run record is a run that cannot
    be repeated, and a batch would discover it half way through rather than at
    the point the value was chosen.
    """
    if not MIN_RUNS <= count <= MAX_RUNS:
        raise ValueError(
            f"a batch is between {MIN_RUNS} and {MAX_RUNS} runs, not {count}: "
            "fewer cannot carry a per-type rate worth reporting, and more than "
            "thirty is more than the scoring campaign can take by hand."
        )
    return _distinct(
        lambda index, attempt: int(
            derive_unit(base_seed, "run", index, attempt) * (SEED_MAX + 1)
        ),
        count,
    )


def derive_window(
    corpus: Window, seed: int, duration_seconds: int, attempt: int = 0
) -> Window:
    """Where in the recorded hour one run replays from.

    Whole seconds, so the start that goes onto the run record reads as a time
    rather than as an artefact of the derivation. `attempt` is the retry key
    `derive_windows` uses and is not something a caller needs: a run's window is
    read back from its row, never re-derived, so a collided window is recorded
    as itself rather than recomputed.
    """
    span = int((corpus.end - corpus.start).total_seconds())
    if span < duration_seconds:
        raise ValueError(
            f"the corpus is shorter than the run: {span} s recorded, "
            f"{duration_seconds} s asked for. Shortening the run silently would "
            "produce a row whose recorded duration describes something other "
            "than what was replayed."
        )

    latitude = span - duration_seconds
    offset = min(int(derive_unit(seed, "window", attempt) * (latitude + 1)), latitude)
    start = corpus.start + timedelta(seconds=offset)
    return Window(start=start, end=start + timedelta(seconds=duration_seconds))


def derive_windows(
    corpus: Window, seeds: Sequence[int], duration_seconds: int
) -> tuple[Window, ...]:
    """One window per run, no two alike.

    Derived for the batch rather than per seed, because distinctness is a
    property of a set and cannot be guaranteed by a function that sees one
    member of it. See the module docstring for the measurement that says this
    is a real collision rather than a theoretical one.
    """
    ordered = tuple(seeds)
    return _distinct(
        lambda index, attempt: derive_window(
            corpus, ordered[index], duration_seconds, attempt
        ),
        len(ordered),
    )


class RunOutcome(_Frozen):
    """What one run of a batch did, whether or not it finished.

    A failed run is described rather than omitted: the batch is required to
    record and skip, and a report that simply has fewer rows than the count it
    was asked for tells a later reader nothing about which run went missing or
    why.
    """

    index: int
    seed: int
    scenario_type: str
    start: datetime
    duration_seconds: int
    run_id: int | None = None
    rf_accepted: int = 0
    rf_quarantined: int = 0
    track_accepted: int = 0
    track_quarantined: int = 0
    #: Aircraft this run actually staged on, counted from the answer key rather
    #: than predicted from the seed. Reported per run because detectability
    #: varies with it and the variation sits inside a batch.
    aircraft_staged: int = 0
    completed: bool = False
    error: str | None = None


class BatchSummary(_Frozen):
    """What a batch did, run by run."""

    base_seed: int
    scenario_type: str
    runs: tuple[RunOutcome, ...]
    seconds: float

    @property
    def completed(self) -> int:
        return sum(1 for run in self.runs if run.completed)

    @property
    def failed(self) -> int:
        return sum(1 for run in self.runs if not run.completed)

    @property
    def staged_nothing(self) -> int:
        """Completed runs whose answer key names no aircraft.

        Observed on the first real batch: twenty coverage-gap runs staged
        between zero and eleven aircraft, and one staged none. Such a run is
        data-identical to a control while its row claims a type, so it cannot
        contribute to recall -- and counting it as a miss would score the
        detector for something it was never shown. Surfaced here because a
        campaign is read as a summary, and nobody notices a zero in row four of
        thirty.
        """
        return sum(1 for run in self.runs if run.completed and not run.aircraft_staged)

    def render(self) -> str:
        header = (
            f"scenario:   {self.scenario_type}\n"
            f"base seed:  {self.base_seed}\n"
            f"runs:       {len(self.runs)} ({self.completed} completed, "
            f"{self.failed} failed)\n"
            f"staged none: {self.staged_nothing} of {self.completed} completed "
            "-- these cannot contribute to recall\n"
            f"seconds:    {self.seconds:.2f}\n\n"
            f"{'run':>3}  {'seed':>10}  {'window':>19}  {'rf':>6}  "
            f"{'track':>6}  {'aircraft':>8}  outcome"
        )
        rows = [
            f"{run.index:>3}  {run.seed:>10}  {run.start:%Y-%m-%d %H:%M:%S}  "
            f"{run.rf_accepted:>6}  {run.track_accepted:>6}  "
            f"{run.aircraft_staged:>8}  "
            + ("ok" if run.completed else f"FAILED: {run.error}")
            for run in self.runs
        ]
        return "\n".join([header, *rows])


def execute_run(
    layout: RfLayout,
    spec: RunSpec,
    *,
    extract: Path,
    repository: ObservationRepository,
    pseudonymiser: Pseudonymiser,
    session_factory: sessionmaker[Session],
    excluded: frozenset[str] = frozenset(),
) -> RunOutcome:
    """One run, both halves, under one run id.

    The order is fixed and each step depends on the one before it. The row is
    opened with what the run *intends* to stage, so a run that dies part-way
    still says what it was attempting; the finished answer key is written at the
    end, because which aircraft were actually touched is a property of the
    corpus rather than of the seed; and completion is marked last of all, after
    both halves have committed (`db-007`).

    **Both halves, whatever the type.** `normal-baseline` and `rf-sensor-fault`
    stage nothing on the tracks and still replay them, because the rules that
    read both sources can only be silent for the right reason if they were shown
    both.

    **The track half is recorded as replayed, not synthetic.** A perturbed row
    is a real recorded observation that a scenario edited, not one the generator
    invented, and `data_mode` describes where an observation came from. What
    makes the run synthetic is on the run record, where a detector cannot read
    it. The consequence is that `op-001`'s badge has to key off the run rather
    than off a track observation's mode.

    Failures after the row exists are caught and returned rather than raised, so
    the batch above can record and skip without losing the run id. A failure
    opening the row propagates: there is nothing yet to describe.
    """
    incident = plan_incident(layout, spec)
    perturbation = plan_track_perturbation(layout, spec)
    perturber = (
        None
        if perturbation is None
        else TrackPerturber(
            perturbation, pseudonymiser=pseudonymiser, excluded=excluded
        )
    )

    run_id = create_scenario_run(
        session_factory,
        scenario_type=spec.scenario_type.value,
        parameters=spec.as_parameters(),
        seed=spec.seed,
        ground_truth=ground_truth(spec, incident),
    )
    outcome = RunOutcome(
        index=0,
        seed=spec.seed,
        scenario_type=spec.scenario_type.value,
        start=spec.start,
        duration_seconds=spec.duration_seconds,
        run_id=run_id,
    )

    try:
        rf = emit_run(layout, spec, run_id, repository, pseudonymiser)
        tracks = replay_window(
            extract,
            Window(
                start=spec.start,
                end=spec.start + timedelta(seconds=spec.duration_seconds),
            ),
            IngestContext(data_mode=DataMode.REPLAYED, scenario_run_id=run_id),
            repository,
            pseudonymiser,
            transform=None if perturber is None else perturber.apply,
        )
        truth = ground_truth(spec, incident, perturber)
        record_ground_truth(session_factory, run_id, truth)
        complete_scenario_run(session_factory, run_id)
    except Exception as error:  # noqa: BLE001 -- recorded, not swallowed
        return outcome.model_copy(update={"error": f"{type(error).__name__}: {error}"})

    return outcome.model_copy(
        update={
            "rf_accepted": rf.accepted,
            "rf_quarantined": rf.quarantined,
            "track_accepted": tracks.accepted,
            "track_quarantined": tracks.quarantined,
            "aircraft_staged": len(truth["aircraft"]),
            "completed": True,
        }
    )


def run_batch(
    layout: RfLayout,
    *,
    scenario_type: ScenarioType | str,
    base_seed: int,
    count: int,
    corpus: Window,
    duration_seconds: int,
    extract: Path,
    repository: ObservationRepository,
    pseudonymiser: Pseudonymiser,
    session_factory: sessionmaker[Session],
    parameters: BaselineParameters | None = None,
    incident: IncidentParameters | None = None,
    excluded: frozenset[str] = frozenset(),
) -> BatchSummary:
    """`count` runs from one base seed, unattended.

    A run that raises is recorded and stepped over. That is the item's own first
    failure case and it is not defensive programming: a campaign that stops at
    run seven because the database blinked has wasted the six before it and
    produced nothing to look at, and the run that failed is exactly the one
    worth reading about afterwards.
    """
    resolved = ScenarioType(scenario_type)
    staging = IncidentParameters() if incident is None else incident
    if resolved is not ScenarioType.NORMAL_BASELINE and (
        staging.start_offset_s >= duration_seconds
    ):
        # Found by running `make generate` for the first time: twenty runs of
        # aircraft-coverage-gap reported ok with zero aircraft staged, because
        # a 120-second run with the default 120-second offset puts the whole
        # incident after the run ends. Every reading was then byte-identical to
        # the quiet run while the answer key claimed a type -- twenty mislabelled
        # controls, and nothing anywhere said so.
        raise ValueError(
            f"an incident starting {staging.start_offset_s} s into a "
            f"{duration_seconds} s run stages nothing: every run in this batch "
            "would claim a scenario type and contain no incident, which is a "
            "mislabelled control rather than a scenario."
        )
    seeds = derive_seeds(base_seed, count)
    windows = derive_windows(corpus, seeds, duration_seconds)
    started = perf_counter()

    outcomes: list[RunOutcome] = []
    for index, (seed, window) in enumerate(zip(seeds, windows, strict=True)):
        spec = RunSpec(
            scenario_type=resolved,
            parameters=BaselineParameters() if parameters is None else parameters,
            incident=IncidentParameters() if incident is None else incident,
            seed=seed,
            start=window.start,
            duration_seconds=duration_seconds,
        )
        try:
            outcome = execute_run(
                layout,
                spec,
                extract=extract,
                repository=repository,
                pseudonymiser=pseudonymiser,
                session_factory=session_factory,
                excluded=excluded,
            )
        except Exception as error:  # noqa: BLE001 -- the row itself failed
            outcome = RunOutcome(
                index=index,
                seed=seed,
                scenario_type=resolved.value,
                start=window.start,
                duration_seconds=duration_seconds,
                error=f"{type(error).__name__}: {error}",
            )
        outcomes.append(outcome.model_copy(update={"index": index}))

    return BatchSummary(
        base_seed=base_seed,
        scenario_type=resolved.value,
        runs=tuple(outcomes),
        seconds=perf_counter() - started,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.pipeline",
        description=(
            "Generate a batch of scenario runs, each driven through the Data "
            "Abstraction Layer into the database."
        ),
    )
    parser.add_argument("--scenario-type", required=True, help="one of the five types")
    parser.add_argument(
        "--base-seed",
        type=int,
        required=True,
        help="the one value the whole batch reproduces from",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=MIN_RUNS,
        help=f"how many runs, between {MIN_RUNS} and {MAX_RUNS} (default: %(default)s)",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=DEFAULT_RUN_SECONDS,
        help="simulated seconds per run (default: %(default)s)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"directory holding {MANIFEST_NAME} (default: %(default)s)",
    )

    # The incident dials. Exposed because `scn-002` made spectral extent a
    # *parameter* of the two interference types rather than a sixth type, which
    # only means anything if a campaign can actually turn it. They are constant
    # within a batch and vary between batches -- see the module note on what
    # that leaves for eval-001.
    staging = parser.add_argument_group("incident")
    defaults = IncidentParameters()
    staging.add_argument(
        "--incident-offset-s",
        type=int,
        default=defaults.start_offset_s,
        help="simulated seconds from a run's start to its incident "
        "(default: %(default)s)",
    )
    staging.add_argument(
        "--incident-duration-s",
        type=int,
        default=defaults.duration_s,
        help="how long the incident lasts (default: %(default)s)",
    )
    staging.add_argument(
        "--radius-km",
        type=float,
        default=defaults.radius_km,
        help="how far the affected zone reaches (default: %(default)s)",
    )
    staging.add_argument(
        "--elevation-db",
        type=float,
        default=defaults.elevation_db,
        help="how far the noise floor rises inside the zone (default: %(default)s)",
    )
    staging.add_argument(
        "--spectral-extent",
        default=defaults.spectral_extent.value,
        help="narrowband (the navigation slice) or broadband (default: %(default)s)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    env_file: Path | None = DEFAULT_ENV_FILE,
    stdout: TextIO | None = None,
) -> int:
    """Run a batch. Returns an exit code; never raises for an expected failure.

    Everything that can fail without a database fails before `init_engine`, in
    the order the failures are cheapest to fix: the arguments, then the seed,
    then the corpus. A batch that opened run rows and then discovered it had no
    corpus would leave twenty orphans behind (`adp-007`).
    """
    out = stdout if stdout is not None else sys.stdout
    args = build_parser().parse_args(argv)

    try:
        scenario_type = ScenarioType(args.scenario_type)
    except ValueError:
        print(
            f"{args.scenario_type!r} is not one of the five scenario types: "
            f"{', '.join(member.value for member in ScenarioType)}.",
            file=sys.stderr,
        )
        return 2

    try:
        derive_seeds(args.base_seed, args.runs)
        incident = IncidentParameters(
            start_offset_s=args.incident_offset_s,
            duration_s=args.incident_duration_s,
            radius_km=args.radius_km,
            elevation_db=args.elevation_db,
            spectral_extent=SpectralExtent(args.spectral_extent),
        )
    except (ValidationError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    # Compose passes an unset host variable through as an empty string, and
    load_seed_environment(env_file)

    try:
        pseudonymiser = Pseudonymiser.from_environment()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    data_dir = Path(args.data_dir)
    manifest_path = data_dir / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(f"cannot read manifest {manifest_path}: {error}", file=sys.stderr)
        return 2

    extract = data_dir / EXTRACT_NAME
    if not extract.is_file():
        print(
            f"cannot read {extract}: the corpus is gitignored and is rebuilt "
            "from the manifest by `python -m app.corpus.build`.",
            file=sys.stderr,
        )
        return 2

    try:
        corpus = available_window(manifest)
        layout = load_layout()
        excluded = load_exclusions(data_dir / EXCLUSIONS_NAME)
    except (KeyError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2

    init_engine()
    try:
        summary = run_batch(
            layout,
            scenario_type=scenario_type,
            base_seed=args.base_seed,
            count=args.runs,
            corpus=corpus,
            duration_seconds=args.duration_seconds,
            extract=extract,
            repository=PostgisObservationRepository(get_sessionmaker()),
            pseudonymiser=pseudonymiser,
            session_factory=get_sessionmaker(),
            incident=incident,
            excluded=excluded,
        )
    except ValueError as error:
        # A batch configured so that no run can stage its own type. Nothing has
        # been written: this is the first thing `run_batch` checks.
        print(str(error), file=sys.stderr)
        return 2
    finally:
        dispose_engine()

    print(summary.render(), file=out)
    # A batch that recorded a failure exits non-zero: the runs it did complete
    # are still there, and a command that reports success over a partial
    # campaign cannot be used in a script.
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
