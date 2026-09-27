"""Draw the twenty packages the scored campaign is about. Spec: eval-004.

**This script spends nothing and must run before the one that does.** It is
the pre-registration of the corpus: `docs/scoring_rubric.md` says the sample
is drawn and committed before the first scored generation, and the argument
is that an instrument that provably predates its results is worth nothing if
the material does not. A sample drawn after seeing how the first few packages
turned out is a sample drawn to produce an answer.

Its output, `scored_sample.json`, is **committed**, and `scored_campaign.py`
reads it rather than redrawing. That split is what makes "the corpus was
fixed first" a property of an artefact in the repository rather than of a
promise -- one script doing both could not enforce the ordering it depends on,
and `ai-012` refuses to invent a sample for the same reason.

The join that reaches ground truth happens **here, in the open**: a bundle
carries no scenario type (`api-009`, `evb-001`), so the run's type is read
from its own row and recorded beside each entry. It never enters a bundle and
never reaches a model or a scorer.

Only ids, kinds and scenario types are written. The bundles stay in the
database: they carry pseudonymised aircraft identifiers, and NFR-405 keeps
those out of anything committed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.bundles import stored_bundles_for_run
from app.evaluation.sampling import PER_KIND, draw_sample

#: Drawn 2026-09-28 and fixed here before the sample was taken, so the
#: number cannot be chosen after seeing which twenty it produces. A seed is
#: a value, not a secret.
SEED = 20260928

OUT = Path(__file__).with_name("scored_sample.json")

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

print(_corpus.describe())
print(f"seed       {SEED}")
print(f"per kind   {PER_KIND}\n", flush=True)

with factory.begin() as session:
    runs = session.execute(
        text(
            f"SELECT DISTINCT r.id, r.scenario_type FROM evidence_bundles b "
            f"JOIN scenario_runs r ON r.id = b.scenario_run_id "
            f"WHERE {_corpus.run_filter('r')} ORDER BY 1"
        )
    ).all()

scenario_types = {run_id: scenario_type for run_id, scenario_type in runs}
available = [
    pair for run_id, _ in runs for pair in stored_bundles_for_run(factory, run_id)
]
print(f"{len(available)} stored bundles from {len(runs)} runs", flush=True)
if not available:
    raise SystemExit(
        "no stored bundles for this corpus. Run corpus/bundle_end_to_end.py "
        "first -- it is what writes them."
    )

sample = draw_sample(available, scenario_types=scenario_types, seed=SEED)

print("\n" + "=" * 78)
print("THE TWENTY, AND WHERE EACH CAME FROM")
print("=" * 78)
for entry in sample.entries:
    print(
        f"  bundle {entry.bundle_id:>6}  {entry.kind:<28} "
        f"{entry.scenario_type:<24} {len(entry.bundle.evidence):>3} items"
    )

print("\n" + "=" * 78)
print("WHAT IT DREW FROM")
print("=" * 78)
for kind, ids in sorted(sample.population.items()):
    print(f"  {kind:<28} {len(ids):>3} available")
print(
    "\n  With the seed above, these two lists are enough to re-run the draw\n"
    "  exactly. That is the claim, and it is stronger than a sentence\n"
    "  describing the rule -- which would be a second copy of the code."
)

by_type: dict[str, int] = {}
for entry in sample.entries:
    by_type[entry.scenario_type] = by_type.get(entry.scenario_type, 0) + 1
print("\n  scenario types drawn (recorded, never stratified on):")
for scenario_type, count in sorted(by_type.items()):
    print(f"    {scenario_type:<26} {count}")

OUT.write_text(json.dumps(sample.as_json(), indent=2, sort_keys=True) + "\n")
print(f"\nwritten to {OUT.name} -- commit it before running scored_campaign.py")
