"""Does every stored run re-derive its own seed? Spec: eval-001.

**The item's only failure case, taken as a measurement for the first time.**
`eval-001` says a batch that cannot be reproduced from its recorded base seed
fails, "since every downstream metric would then be unverifiable" -- and until
`scn-008` that claim could not be evaluated at all. The base seed was printed by
the batch summary and never stored, so of the base seeds behind the first 240
runs exactly one survives anywhere. An item whose single failure case cannot be
checked is not a passing item, and nothing in the backlog said so.

**What it checks is the record, not the function.** `scn-008`'s suite asserts
that a constructed run spec re-derives its own seed; between that and this lie a
JSON round-trip through `scenario_runs.parameters`, a base seed that comes back
as text to be cast, and a batch index that indexes a list. This reads what a
stranger with nothing but the database would read.

**Every run, not just corpus v2.** The claim is about the store rather than about
one corpus, so this deliberately does not use `_corpus.run_filter()`: the
development batch and any batch generated from the screen are part of the
population, and a check scoped to the corpus of record would not notice a
generator that had stopped recording provenance. Batches are reported
individually so a single bad one cannot be averaged away.

**A run recording no batch is unprovenanced, never wrong.** A run generated
outside a batch records nothing rather than inventing a batch of one (`scn-008`),
and corpus v1's runs predate the column entirely. Counted in their own column,
because reporting them as mismatches would call an older corpus broken rather
than uncheckable.

Read-only. It opens no transaction and writes nothing, so it needs no guard.

Run: `make measure SCRIPT=corpus/batch_reproducibility.py CORPUS=dev` from the
repository root. `CORPUS` is accepted and unused -- see above.
"""

import os
from collections import defaultdict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.pipeline import MAX_RUNS, MIN_RUNS, derive_seeds

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

with factory() as session:
    rows = (
        session.execute(
            text("SELECT id, seed, scenario_type, parameters FROM scenario_runs ORDER BY id")
        )
        .mappings()
        .all()
    )

print(f"{len(rows)} runs in the store, ids {rows[0]['id']} to {rows[-1]['id']}")

# Grouped by the batch a run says it came from. **One batch per scenario type
# per base seed**, which is what the run rows actually record: a base seed
# behind 100 runs carries `batch_runs` of 20, because the pipeline ran one
# twenty-run batch for each of the five types from that seed. Grouping on the
# base seed alone would report a batch of 20 holding 100 runs.
batches: dict[tuple[int, str, int], list[dict]] = defaultdict(list)
unprovenanced: list[dict] = []
for row in rows:
    recorded = row["parameters"]
    if "base_seed" not in recorded:
        unprovenanced.append(row)
        continue
    batches[
        (int(recorded["base_seed"]), row["scenario_type"], int(recorded["batch_runs"]))
    ].append(row)

print(f"{len(batches)} batches, {len(unprovenanced)} runs recording no batch\n")

print(
    f"  {'base seed':>12} {'scenario type':26} {'size':>5} {'runs':>5} "
    f"{'re-derived':>11} {'mismatched':>11}"
)
total_ok = total_bad = 0
mismatches: list[tuple[int, int, int]] = []
for (base_seed, kind, size), members in sorted(batches.items()):
    seeds = derive_seeds(base_seed, size)
    ok = bad = 0
    for row in members:
        index = int(row["parameters"]["batch_index"])
        if seeds[index] == row["seed"]:
            ok += 1
        else:
            bad += 1
            mismatches.append((row["id"], row["seed"], seeds[index]))
    total_ok += ok
    total_bad += bad
    print(
        f"  {base_seed:12d} {kind:26} {size:5d} {len(members):5d} {ok:11d} {bad:11d}"
    )

scored = total_ok + total_bad
print(f"\n{total_ok} of {scored} runs re-derive their own seed exactly")
if mismatches:
    print("MISMATCHED -- run id, stored seed, the seed its own record derives:")
    for run_id, stored, expected in mismatches:
        print(f"  run {run_id}: stored {stored}, record derives {expected}")
else:
    print("no mismatches: every batch in the store reproduces from its recorded seed")

# The seed-matching every control measurement in this project rests on, verified
# here for the first time. `anom-006`'s closure is argued over "60 seed-matched
# pairs -- same seed, same corpus window, same aircraft", `anom-004`'s radius over
# "eight triples of eight", and `scn-007`'s floor over "40 pairs generated after
# scn-006". All of those depend on one arm's run at index i carrying the *same*
# derived seed as another arm's run at index i, and nothing anywhere asserts it.
# It follows from the derivation being keyed on the base seed and the index alone
# -- which is exactly the kind of "follows from" that is worth checking once
# against the rows, since a generator keyed additionally on the scenario type
# would produce a corpus whose every matched-pair figure compared unmatched runs.
print("\nSEED MATCHING ACROSS ARMS -- one arm's run at index i against another's")
by_position: dict[tuple[int, int], dict[str, int]] = defaultdict(dict)
for (base_seed, kind, _size), members in batches.items():
    for row in members:
        by_position[(base_seed, int(row["parameters"]["batch_index"]))][kind] = row["seed"]

shared = [p for p, seeds in by_position.items() if len(set(seeds.values())) == 1]
split = {p: seeds for p, seeds in by_position.items() if len(set(seeds.values())) > 1}
arms = {len(seeds) for seeds in by_position.values()}
print(
    f"  {len(by_position)} (base seed, index) positions, "
    f"{sorted(arms)} arms at each"
)
if split:
    print(f"  NOT MATCHED at {len(split)} positions: {sorted(split)[:5]}")
else:
    print(
        f"  every one of the {len(shared)} positions carries one seed across all "
        "of its arms, so a matched pair really is matched"
    )

# A batch outside the bounds scn-003 enforces would still re-derive, and would
# still be a batch eval-001 does not describe. Reported rather than asserted,
# because the bounds moved once already and a measurement that refused would
# have to be edited to record the fact.
outside = sorted(
    {(bs, size) for (bs, _kind, size) in batches if not MIN_RUNS <= size <= MAX_RUNS}
)
print(
    f"\nbatch sizes within {MIN_RUNS}-{MAX_RUNS}: "
    + ("all" if not outside else f"NO -- {outside}")
)
if unprovenanced:
    print(
        f"\n{len(unprovenanced)} runs record no batch and are therefore "
        "uncheckable rather than wrong (scn-008): ids "
        f"{[row['id'] for row in unprovenanced][:12]}"
    )
