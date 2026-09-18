"""Batch execution: seeds, windows, and the run record. Spec: scn-003 (pass 1 of 2).

A batch is twenty to thirty runs produced from one number, and this pass is the
arithmetic that makes that sentence true. The executor, the failure isolation
and the operator command are pass 2.

Three properties, and the second and third were not in the item as first
written:

* **Every run gets its own seed, derived rather than drawn.** Keyed derivation,
  as `scn-001` chose for readings, so a run's seed is a function of the base and
  the run's own index and not of how many runs happened to precede it.
* **Every run gets its own window of the corpus.** There are seven receivers and
  twenty to thirty runs, so several runs in a batch necessarily stage their
  incident at the same place. If they also replayed the same stretch of traffic
  they would differ only in invented noise, and a batch of thirty would carry
  far less variation than its size suggests.
* **The run row can reproduce its own stream.** `as_parameters` recorded the
  baseline and incident settings and neither the start nor the duration, so
  `scn-001`'s reproduction property held in the test suite -- where the window is
  a module constant -- and not from the database. A batch reproducible from one
  value whose rows cannot regenerate their own readings is not reproducible in
  the sense the evaluation needs.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.adapters.opensky import Window
from app.pipeline import (
    MAX_RUNS,
    MIN_RUNS,
    _distinct,
    derive_seeds,
    derive_window,
    derive_windows,
)
from app.scenario.emitter import (
    BaselineParameters,
    RunSpec,
    emit_rf,
    stream_digest,
)
from app.scenario.incident import IncidentParameters, ScenarioType, plan_incident
from app.scenario.layout import RfLayout, load_layout
from app.scenario.seeding import SEED_MAX

BASE_SEED = 20220627

#: The corpus is one recorded hour, and every run's window has to fit inside it.
CORPUS = Window(
    start=datetime(2022, 6, 27, 12, 0, 0, tzinfo=UTC),
    end=datetime(2022, 6, 27, 13, 0, 0, tzinfo=UTC),
)

RUN_SECONDS = 900
BATCH = 25

#: `scn-001`'s rule, applied to the module that sits outside its package.
#: `random` is unseeded by default and order-dependent when it is not, `time`
#: is the wall clock, `uuid` is both.
FORBIDDEN_IMPORTS = frozenset({"random", "time", "uuid"})

#: The one name from `time` the batch module may hold. Narrowed during pass 2,
#: when the rule as first written rejected the implementation: `perf_counter`
#: measures how long the batch took and has an undefined epoch, so it cannot
#: date anything and cannot reach a generated value. What the rule is actually
#: about is a *clock reading* influencing data, which is `time.time()` and
#: friends -- so a plain `import time` stays forbidden, since it puts those one
#: attribute away.
ALLOWED_TIME_NAMES = frozenset({"perf_counter"})


@pytest.fixture()
def layout() -> RfLayout:
    return load_layout()


def _spec(*, seed: int = BASE_SEED, start: datetime | None = None) -> RunSpec:
    return RunSpec(
        scenario_type=ScenarioType.GNSS_DEGRADATION,
        parameters=BaselineParameters(),
        incident=IncidentParameters(),
        seed=seed,
        start=start if start is not None else CORPUS.start,
        duration_seconds=RUN_SECONDS,
    )


# ------------------------------------------------ one number, N distinct runs


def test_a_batch_derives_a_distinct_seed_for_every_run() -> None:
    """Two runs sharing a seed is the item's own failure case: they would stage
    the same incident in the same place and count as two observations of it."""
    # spec: scn-003
    for count in (MIN_RUNS, BATCH, MAX_RUNS):
        seeds = derive_seeds(BASE_SEED, count)
        assert len(seeds) == count
        assert len(set(seeds)) == count


def test_the_same_base_seed_derives_the_same_seeds() -> None:
    # spec: scn-003
    assert derive_seeds(BASE_SEED, BATCH) == derive_seeds(BASE_SEED, BATCH)


def test_a_different_base_seed_derives_different_seeds() -> None:
    """The trap arm, one level up from `scn-001`'s: a derivation that ignores
    the base value gives a perfectly reproducible batch of the wrong runs."""
    # spec: scn-003, scn-001
    first = set(derive_seeds(BASE_SEED, BATCH))
    second = set(derive_seeds(BASE_SEED + 1, BATCH))

    assert not first & second


def test_a_run_seed_does_not_depend_on_the_size_of_the_batch() -> None:
    """Keyed derivation rather than a sequence, for the reason `scn-001` gives:
    under a drawn sequence, run 19 of a batch of twenty and run 19 of a batch of
    thirty would be the same run, but asking for one more run tomorrow would
    renumber nothing and reproduce nothing."""
    # spec: scn-003, scn-001
    twenty = derive_seeds(BASE_SEED, MIN_RUNS)
    thirty = derive_seeds(BASE_SEED, MAX_RUNS)

    assert thirty[:MIN_RUNS] == twenty


def test_every_derived_seed_fits_the_run_record() -> None:
    """`scenario_runs.seed` is a 32-bit signed column. A seed that does not
    round-trip through the row is a run that cannot be repeated -- and a batch
    would discover it half way through, hours after the value was chosen."""
    # spec: scn-003, db-001
    assert all(0 <= seed <= SEED_MAX for seed in derive_seeds(BASE_SEED, MAX_RUNS))


def test_a_run_count_outside_twenty_to_thirty_is_refused() -> None:
    # spec: scn-003
    for count in (0, 1, MIN_RUNS - 1, MAX_RUNS + 1, 100):
        with pytest.raises(ValueError, match="between"):
            derive_seeds(BASE_SEED, count)

    assert len(derive_seeds(BASE_SEED, MIN_RUNS)) == MIN_RUNS
    assert len(derive_seeds(BASE_SEED, MAX_RUNS)) == MAX_RUNS


# ------------------------------------------- each run sees its own traffic


def test_every_window_lies_inside_the_corpus() -> None:
    """A window reaching past the recorded hour would replay nothing for part of
    its length, which reads downstream as a coverage gap nobody staged."""
    # spec: scn-003, adp-001
    for seed in derive_seeds(BASE_SEED, BATCH):
        window = derive_window(CORPUS, seed, RUN_SECONDS)
        assert CORPUS.start <= window.start
        assert window.end <= CORPUS.end


def test_every_window_is_exactly_the_run_length() -> None:
    # spec: scn-003
    for seed in derive_seeds(BASE_SEED, BATCH):
        window = derive_window(CORPUS, seed, RUN_SECONDS)
        assert window.end - window.start == timedelta(seconds=RUN_SECONDS)


def test_the_window_is_determined_by_the_seed() -> None:
    # spec: scn-003
    assert derive_window(CORPUS, BASE_SEED, RUN_SECONDS) == derive_window(
        CORPUS, BASE_SEED, RUN_SECONDS
    )
    assert derive_window(CORPUS, BASE_SEED, RUN_SECONDS) != derive_window(
        CORPUS, BASE_SEED + 1, RUN_SECONDS
    )


def test_the_runs_in_a_batch_never_share_a_window() -> None:
    """The failure case this decision exists for. Seven receivers and
    twenty-five runs means several runs stage at the same centre; sharing a
    window as well would make those runs near-duplicates on the track side,
    differing only in the invented noise.

    Asserted over four base seeds rather than one, and the batch derivation is
    asked for the whole set rather than each window separately. Measured
    2026-09-12, before implementing: deriving an offset per seed in whole
    seconds gives 25 distinct windows for base 20220627 and 24 for base 1 --
    forty-five minutes of latitude is only 2,701 places to stand, and
    twenty-five draws collide about one time in eight. A test written against
    the fixture's own base would have passed and said nothing, which is why the
    batch guarantees distinctness rather than relying on the space being large.
    """
    # spec: scn-003
    for base in (BASE_SEED, 1, 42, 999983):
        windows = derive_windows(CORPUS, derive_seeds(base, BATCH), RUN_SECONDS)

        assert len(windows) == BATCH
        assert len(set(windows)) == BATCH


def test_a_corpus_shorter_than_the_run_is_refused() -> None:
    """Loudly, before anything is written: silently shortening the run would
    produce a batch whose rows disagree with their own recorded duration."""
    # spec: scn-003
    short = Window(start=CORPUS.start, end=CORPUS.start + timedelta(seconds=60))

    with pytest.raises(ValueError, match="shorter"):
        derive_window(short, BASE_SEED, RUN_SECONDS)


def test_a_corpus_exactly_one_run_long_gives_the_only_window() -> None:
    """The edge the derivation must clamp rather than overrun."""
    # spec: scn-003
    exact = Window(
        start=CORPUS.start, end=CORPUS.start + timedelta(seconds=RUN_SECONDS)
    )

    assert derive_window(exact, BASE_SEED, RUN_SECONDS) == exact


# --------------------------------------- the row can regenerate its own run


def test_the_recorded_parameters_carry_the_window() -> None:
    # spec: scn-003, scn-001
    recorded = _spec().as_parameters()

    assert recorded["start"] == CORPUS.start.isoformat()
    assert recorded["duration_seconds"] == RUN_SECONDS
    # `scn-001` still holds: the seed has a column of its own.
    assert "seed" not in recorded


def test_a_run_is_rebuilt_from_what_the_row_records() -> None:
    # spec: scn-003, scn-001
    spec = _spec()

    rebuilt = RunSpec.from_record(
        scenario_type=spec.scenario_type.value,
        parameters=spec.as_parameters(),
        seed=spec.seed,
    )

    assert rebuilt == spec


def test_a_recorded_run_reproduces_its_stream_byte_for_byte(
    layout: RfLayout,
) -> None:
    """The property `scn-001` proves in the suite, proved here from the record
    alone -- which is what a batch reproducible from one value actually needs."""
    # spec: scn-003, scn-001, adp-002
    spec = _spec(start=CORPUS.start + timedelta(seconds=1200))
    original = stream_digest(emit_rf(layout, spec, plan_incident(layout, spec)))

    rebuilt = RunSpec.from_record(
        scenario_type=spec.scenario_type.value,
        parameters=spec.as_parameters(),
        seed=spec.seed,
    )

    assert (
        stream_digest(emit_rf(layout, rebuilt, plan_incident(layout, rebuilt)))
        == original
    )


def test_a_row_with_no_window_cannot_rebuild_its_run(layout: RfLayout) -> None:
    """A row recorded before this pass has no window in it. Refusing loudly is
    the difference between knowing a run cannot be reproduced and quietly
    reproducing a different one under its name."""
    # spec: scn-003
    parameters = _spec().as_parameters()
    del parameters["start"]

    with pytest.raises(ValueError, match="start"):
        RunSpec.from_record(
            scenario_type=ScenarioType.GNSS_DEGRADATION.value,
            parameters=parameters,
            seed=BASE_SEED,
        )


def test_a_row_carrying_an_unknown_parameter_is_refused() -> None:
    """Written after the implementation, to cover a refusal the first pass of
    tests missed -- the coverage gate was satisfied and the branch was not
    exercised at all. Recorded as a deviation rather than quietly repaired.

    A row holding a setting this generator does not know was written by a
    different generator. Dropping the unknown key and emitting anyway would
    produce a stream that is not what the row describes, under the row's own
    answer key.
    """
    # spec: scn-003
    parameters = _spec().as_parameters()
    parameters["antenna_gain_db"] = 3.0

    with pytest.raises(ValueError, match="unrecognised"):
        RunSpec.from_record(
            scenario_type=ScenarioType.GNSS_DEGRADATION.value,
            parameters=parameters,
            seed=BASE_SEED,
        )


def test_a_derivation_that_ignores_its_retry_key_fails_loudly() -> None:
    """Found by mutation rather than by design, and added afterwards.

    Replacing the window offset with a constant turned the batch's
    distinctness loop into an infinite one: every retry returned the same
    value, so the loop never left. A campaign that hangs is worse than one that
    fails, and the hang would arrive in the middle of a batch rather than at
    its first run. Reaches for the private helper deliberately -- a degenerate
    derivation cannot be injected through the public surface, which is the
    point of the guard.
    """
    # spec: scn-003
    with pytest.raises(RuntimeError, match="retry"):
        _distinct(lambda index, attempt: 1, MIN_RUNS)


def test_the_batch_module_reads_no_clock_and_no_unseeded_randomness() -> None:
    """`scn-001` asserts this over `app/scenario/` and the batch module is not
    in that package, so the rule did not reach it.

    Found by mutation, and the mutation is the argument for the test: replacing
    the keyed derivation with `random.Random(base_seed)` left all eighteen
    tests green. Both give the same prefix property -- a sequence seeded once
    produces the same first twenty draws whether you ask for twenty or thirty
    -- so no behavioural test here can separate them. What separates them is
    that a sequence cannot compute run seventeen without computing the sixteen
    before it, and shifts every later value if one more quantity is ever drawn
    per run. That is a constraint rather than an output, so it is asserted as
    one.
    """
    # spec: scn-003, scn-001
    tree = ast.parse(
        (Path(__file__).resolve().parents[1] / "app" / "pipeline.py").read_text(
            encoding="utf-8"
        )
    )

    offences: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offences += [
                f"import {alias.name}"
                for alias in node.names
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS
            ]
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root == "time":
                offences += [
                    f"from time import {alias.name}"
                    for alias in node.names
                    if alias.name not in ALLOWED_TIME_NAMES
                ]
            elif root in FORBIDDEN_IMPORTS:
                offences.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "hash":
                offences.append("hash()")

    assert offences == []


# ---------------------------------------------------------------------------
# scn-008: a run should name the batch it came from.
#
# BatchSummary has always carried the base seed and always printed it in the
# batch report, and the value then reached nothing durable. Of the base seeds
# behind the 240 stored runs exactly one survives anywhere, in a
# pre-registration that happened to quote it -- which is why the regenerated
# corpus has to be reported as a new corpus rather than a repeat.
#
# The point of these tests is not that three numbers are stored. It is that
# storing them makes the run's own seed *checkable*: re-derive it from the
# recorded batch and it must match. A recorded number nobody can check is
# barely better than a lost one.
# ---------------------------------------------------------------------------


def test_a_run_records_the_batch_it_came_from() -> None:
    # spec: scn-008
    spec = _spec().with_batch(base_seed=BASE_SEED, index=7, runs=20)
    parameters = spec.as_parameters()

    assert parameters["base_seed"] == BASE_SEED
    assert parameters["batch_index"] == 7
    assert parameters["batch_runs"] == 20


def test_the_recorded_batch_re_derives_the_runs_own_seed() -> None:
    """The property the three values exist for. Without this they are three
    numbers that cannot be wrong, which is not the same as being right."""
    # spec: scn-008, scn-001
    seeds = derive_seeds(BASE_SEED, 20)
    spec = _spec(seed=seeds[7]).with_batch(base_seed=BASE_SEED, index=7, runs=20)
    parameters = spec.as_parameters()

    re_derived = derive_seeds(parameters["base_seed"], parameters["batch_runs"])
    assert re_derived[parameters["batch_index"]] == spec.seed


def test_a_run_generated_outside_a_batch_records_no_batch() -> None:
    """Rather than inventing a batch of one. A synthetic value here would be
    indistinguishable from a real one, and the field exists to be trusted."""
    # spec: scn-008
    spec = _spec()

    assert spec.batch is None
    parameters = spec.as_parameters()
    assert "base_seed" not in parameters
    assert "batch_index" not in parameters
    assert "batch_runs" not in parameters


def test_a_row_carrying_batch_provenance_still_rebuilds_its_run() -> None:
    """Provenance, not a generation input: `from_record` refuses parameters it
    does not recognise, and these must not trip that refusal."""
    # spec: scn-008, scn-003
    spec = _spec().with_batch(base_seed=BASE_SEED, index=3, runs=25)

    rebuilt = RunSpec.from_record(
        scenario_type=spec.scenario_type.value,
        parameters=spec.as_parameters(),
        seed=spec.seed,
    )

    assert rebuilt.seed == spec.seed
    assert rebuilt.start == spec.start
    assert rebuilt.duration_seconds == spec.duration_seconds
    # Found by mutation: asserting the row rebuilds is not the same as
    # asserting the provenance came back with it. A `from_record` that
    # silently dropped the batch passed every other test here, and the row
    # would then stop naming its batch the moment it made a round trip.
    assert rebuilt.batch == spec.batch
    assert rebuilt == spec


def test_a_row_with_no_batch_still_rebuilds_its_run() -> None:
    """Every one of the 240 runs generated before this item has no batch
    recorded, and those rows stay readable."""
    # spec: scn-008, scn-003
    spec = _spec()

    rebuilt = RunSpec.from_record(
        scenario_type=spec.scenario_type.value,
        parameters=spec.as_parameters(),
        seed=spec.seed,
    )

    assert rebuilt == spec
    assert rebuilt.batch is None


def test_a_rebuilt_run_reproduces_its_stream_with_batch_recorded(
    layout: RfLayout,
) -> None:
    """The batch fields are inert: adding them must not change a single
    emitted reading, or they would be a generation input in disguise."""
    # spec: scn-008, scn-001
    spec = _spec(start=CORPUS.start + timedelta(seconds=1200))
    original = stream_digest(emit_rf(layout, spec, plan_incident(layout, spec)))

    with_batch = spec.with_batch(base_seed=BASE_SEED, index=2, runs=20)

    assert (
        stream_digest(emit_rf(layout, with_batch, plan_incident(layout, with_batch)))
        == original
    )


def test_a_batch_index_outside_its_own_batch_is_refused() -> None:
    """An index past the run count cannot name a run, so the provenance would
    be unverifiable by construction -- the one thing it exists not to be."""
    # spec: scn-008
    with pytest.raises(ValueError, match="batch"):
        _spec().with_batch(base_seed=BASE_SEED, index=20, runs=20)


def test_a_negative_batch_index_is_refused() -> None:
    """Refused by the field constraint rather than by the validator below it,
    which is why this matches on the field and not on the prose."""
    # spec: scn-008
    with pytest.raises(ValueError, match="index"):
        _spec().with_batch(base_seed=BASE_SEED, index=-1, runs=20)


def test_every_run_in_a_batch_records_that_batch() -> None:
    """The item is inert unless the batch entrypoint supplies it, and a
    provenance field that nothing populates is worse than none at all --
    it reads as evidence the batch was recorded."""
    # spec: scn-008, scn-003
    seeds = derive_seeds(BASE_SEED, MIN_RUNS)
    windows = derive_windows(CORPUS, seeds, RUN_SECONDS)

    for index, (seed, window) in enumerate(zip(seeds, windows, strict=True)):
        spec = RunSpec(
            scenario_type=ScenarioType.GNSS_DEGRADATION,
            parameters=BaselineParameters(),
            incident=IncidentParameters(),
            seed=seed,
            start=window.start,
            duration_seconds=RUN_SECONDS,
        ).with_batch(base_seed=BASE_SEED, index=index, runs=MIN_RUNS)

        recorded = spec.as_parameters()
        re_derived = derive_seeds(recorded["base_seed"], recorded["batch_runs"])
        assert re_derived[recorded["batch_index"]] == seed
