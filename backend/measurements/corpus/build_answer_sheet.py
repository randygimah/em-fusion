"""Render the answer sheet for the scoring's second pass. Spec: eval-010.

**Spends nothing and writes one file.** It reads the committed sample, the
scoring pack's own order, and each sampled bundle with its run's ground-truth
record from the database, then writes `scoring_pack/answer_sheet.md`. Nothing
a rater has already scored against is regenerated: the pack, the workbooks
and the arm key are left exactly as they are.

The join to ground truth happens here, in the open, as `draw_scored_sample.py`
does it: a bundle carries no scenario type (`api-009`, `evb-001`), so the run's
record is read from its own row. The log prints counts only; the sheet names
staged aircraft by pseudonym, as the pack it sits beside already does.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.bundles import stored_bundles_for_run
from app.evaluation.answers import build_answer_sheet, pack_order

HERE = Path(__file__).parent
SAMPLE = HERE / "scored_sample.json"
PACK = HERE / "scoring_pack"
OUT = PACK / "answer_sheet.md"

sample = {
    int(entry["bundle_id"]): str(entry["scenario_type"])
    for entry in json.loads(SAMPLE.read_text())["entries"]
}
order = pack_order((PACK / "hypotheses.md").read_text())

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

with factory.begin() as session:
    rows = session.execute(
        text(
            "SELECT b.id, b.scenario_run_id, r.ground_truth "
            "FROM evidence_bundles b JOIN scenario_runs r ON r.id = b.scenario_run_id "
            "WHERE b.id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": sorted(sample)},
    ).all()

run_of = {int(bundle_id): int(run_id) for bundle_id, run_id, _ in rows}
truths = {int(bundle_id): truth for bundle_id, _, truth in rows if truth is not None}
bundles = {
    bundle_id: bundle
    for run_id in sorted(set(run_of.values()))
    for bundle_id, bundle in stored_bundles_for_run(factory, run_id)
    if bundle_id in sample
}

sheet = build_answer_sheet(order=order, sample=sample, truths=truths, bundles=bundles)
OUT.write_text(sheet)

about = Counter(
    (sample[bundle_id], "| **About the staged incident** | Yes |" in section)
    for bundle_id, section in zip(order, sheet.split("## Evidence pack")[1:])
)
print(f"sample       {SAMPLE.name}, {len(sample)} bundles")
print(f"pack order   {len(order)} packs read from hypotheses.md")
print(f"runs         {len(set(run_of.values()))} distinct")
print("\nabout the staged incident, by scenario type:")
for scenario_type in sorted({t for t, _ in about}):
    yes, no = about[(scenario_type, True)], about[(scenario_type, False)]
    print(f"  {scenario_type:26} {yes:2} yes  {no:2} no")
print(f"\nwritten      {OUT.relative_to(HERE)}; nothing else touched")
