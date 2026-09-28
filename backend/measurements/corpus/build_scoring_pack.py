"""Render the pack the second marker receives. Spec: eval-004, second pass.

**Spends nothing and reads nothing from a provider.** It reads the campaign
record written by `scored_campaign.py`, reads the stored hypotheses back out
of the database, and writes three files. Everything it needs already
happened; this only renders it.

**The three files are not for the same audience, and that is the point.**
`hypotheses.md` and `score_sheet.csv` go to the marker. `arm_key.csv` does
not, and is joined only after both markers' sheets are ingested (`eval-006`)
so that a score cannot be attributed to an arm while it is being entered.

The scored generation is generation 1, taken by its ordinal, and it is never
substituted when it fell back -- that rule is `eval-004`'s and lives in the
exporter rather than here, so this script cannot quietly opt out of it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.campaign import generations_from_json
from app.db.bundles import stored_bundles_for_run
from app.db.hypotheses import hypotheses_for_bundle
from app.evaluation.pack import (
    BLINDING_GIVEAWAYS,
    DIMENSIONS,
    JUDGEMENTS,
    as_json,
    build_pack,
)

#: Fixed here rather than passed in, and different from the sample's seed so
#: that knowing one tells you nothing about the other. It decides which arm
#: is A on each pack, so it is the one number that would unblind the whole
#: exercise if it leaked into the marker's files -- it does not, and a test
#: checks the vocabulary of what does.
SHUFFLE_SEED = 20260929

RECORD = Path(__file__).with_name("scored_campaign_record.json")
OUT = Path(__file__).with_name("scoring_pack")

if not RECORD.is_file():
    raise SystemExit(
        f"{RECORD.name} does not exist. The pack is rendered from a campaign "
        "that has run:\n\n    make measure SCRIPT=corpus/scored_campaign.py "
        "CORPUS=v2 CAMPAIGN_CONFIRM=yes\n"
    )

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

generations = generations_from_json(json.loads(RECORD.read_text()))
wanted = sorted({g.bundle_id for g in generations})

with factory.begin() as session:
    run_ids = [
        r[0]
        for r in session.execute(
            text(
                f"SELECT DISTINCT b.scenario_run_id FROM evidence_bundles b "
                f"JOIN scenario_runs r ON r.id = b.scenario_run_id "
                f"WHERE {_corpus.run_filter('r')} ORDER BY 1"
            )
        ).all()
    ]

held = {
    bundle_id: bundle
    for run_id in run_ids
    for bundle_id, bundle in stored_bundles_for_run(factory, run_id)
}
bundles = [(bundle_id, held[bundle_id]) for bundle_id in wanted if bundle_id in held]

# Read every stored hypothesis the record names, straight from the rows the
# campaign wrote. Not from the record: the record says *where* each
# generation went, and the database says what is there -- and the second is
# what a reader could check.
hypotheses = {
    row.id: row.hypothesis
    for bundle_id in wanted
    for row in hypotheses_for_bundle(factory, bundle_id)
}

print(_corpus.describe())
print(f"record     {RECORD.name}, {len(generations)} generations")
print(f"bundles    {len(bundles)} of {len(wanted)} named by the record")
print(f"shuffle    seed {SHUFFLE_SEED}\n", flush=True)

pack = build_pack(
    generations=generations,
    bundles=bundles,
    hypotheses=hypotheses,
    seed=SHUFFLE_SEED,
)

OUT.mkdir(exist_ok=True)
(OUT / "hypotheses.md").write_text(pack.hypotheses_md)
(OUT / "score_sheet.csv").write_text(pack.score_sheet_csv)
(OUT / "arm_key.csv").write_text(pack.arm_key_csv)

shape = as_json(pack)
print("=" * 78)
print("WHAT THE MARKER GETS")
print("=" * 78)
print(f"  evidence packs     {shape['bundles']}")
print(f"  explanations       {shape['items']} ({shape['items_per_bundle']} per pack)")
print(f"  dimensions         {len(DIMENSIONS)} in pass one, {len(JUDGEMENTS)} in pass two")
print(f"  values per marker  {shape['values_per_rater']} in pass one")
print(
    f"\n  That last figure is what the participant information sheet and the\n"
    f"  ethics approval form quote. If it is not 200 here, one of the three\n"
    f"  has moved and the consent is no longer informed by the right number."
)

leaks = [w for w in BLINDING_GIVEAWAYS if w in pack.hypotheses_md.lower()]
print("\n" + "=" * 78)
print("WHAT IS NOT IN WHAT THE MARKER READS")
print("=" * 78)
print(f"  arm vocabulary found in hypotheses.md: {leaks or 'none'}")
if leaks:
    raise SystemExit(
        f"the pack names the arms {leaks}. The comparison is blind and this "
        "would hand the marker a perfect classifier."
    )
print("  arm key written to arm_key.csv, which the marker does not receive.")

print(f"\nwritten to {OUT.name}/ -- hypotheses.md and score_sheet.csv go to the")
print("marker; arm_key.csv is held back until eval-006 ingests both sheets.")
