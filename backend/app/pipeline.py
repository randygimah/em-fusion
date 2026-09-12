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

from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import TypeVar

from app.adapters.opensky import Window
from app.scenario.seeding import SEED_MAX, derive_unit

#: The run count a batch must fall within (`scn-003`, FR-205). A campaign
#: smaller than this cannot carry a per-type rate worth quoting; larger is not
#: forbidden by anything except the cost of scoring it by hand.
MIN_RUNS = 20
MAX_RUNS = 30

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
