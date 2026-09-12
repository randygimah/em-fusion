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

from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.opensky import Window
from app.pipeline import MAX_RUNS, MIN_RUNS, derive_seeds, derive_window
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


def test_the_runs_in_a_batch_do_not_all_share_one_window() -> None:
    """The failure case this decision exists for. Seven receivers and
    twenty-five runs means several runs stage at the same centre; sharing a
    window as well would make those runs near-duplicates on the track side,
    differing only in the invented noise."""
    # spec: scn-003
    windows = {
        derive_window(CORPUS, seed, RUN_SECONDS)
        for seed in derive_seeds(BASE_SEED, BATCH)
    }

    assert len(windows) == BATCH


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
