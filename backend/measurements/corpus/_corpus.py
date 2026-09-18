"""Which runs a measurement is about. Import this rather than hardcoding ids.

The database holds **two corpora**. Runs 1-240 are the first one, generated
across three different generator versions -- runs 1-20 at 600 s where
everything later is 900 s, and runs 1-100 before scn-006 put the airborne
gate in, so their answer keys name a mean of about five staged aircraft
against fewer than two afterwards. Runs 241 onward are corpus v2: one
generator, one run length, both anom-014 and scn-007 active from run one.

Mixing them is not a theoretical hazard. It already happened once: scn-007's
floor was first measured across the scn-006 boundary and the figure had to
be withdrawn, because the high-staged cells of that curve could only be
drawn from the pre-gate blocks, where most staged aircraft were parked and
undetectable by construction.

**The discriminator is the base seed, not the run id.** scn-008 records the
base seed a run came from on the run row; nothing before it did. So
`parameters->>'base_seed' IS NOT NULL` names corpus v2 exactly, and it keeps
naming it correctly if ids shift, if a batch is re-run, or if a third corpus
is ever generated -- none of which an id range survives.
"""
from __future__ import annotations

import os

#: Corpus v2's base seeds, drawn 2026-09-18 and recorded in CORPUS_V2_PLAN.md
#: before generation. A base seed is a value and not a secret.
BASE_SEEDS = (1412660662, 965530111, 655209063)

#: Corpus v1: ids 1-240, no base seed recorded on any row.
V1 = "v1"
#: Corpus v2: every run carries its base seed (`scn-008`).
V2 = "v2"


def which() -> str:
    """Which corpus this run of the script is about. Override with CORPUS=v1."""
    choice = os.environ.get("CORPUS", V2)
    if choice not in (V1, V2):
        raise SystemExit(f"CORPUS must be {V1!r} or {V2!r}, not {choice!r}")
    return choice


def run_filter(alias: str = "") -> str:
    """A SQL predicate selecting the current corpus's runs.

    `alias` is the table alias to qualify with, if the query needs one.
    Returns a bare predicate so it can be dropped into an existing WHERE.
    """
    column = f"{alias}.parameters" if alias else "parameters"
    if which() == V2:
        return f"({column}->>'base_seed') IS NOT NULL"
    return f"({column}->>'base_seed') IS NULL"


def describe() -> str:
    """One line naming what is being measured, for the top of a log."""
    if which() == V2:
        return (
            f"corpus v2 -- one generator, 900 s runs, anom-014 and scn-007 active; "
            f"base seeds {', '.join(str(s) for s in BASE_SEEDS)}"
        )
    return (
        "corpus v1 -- ids 1-240, THREE generator versions (600 s runs 1-20, "
        "pre-scn-006 runs 1-100). Figures from it are not comparable with v2."
    )
