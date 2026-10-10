"""Render the second rater's ten packs. Spec: eval-011.

**Spends nothing, and writes one folder the first rater never used.** It
draws ten of the twenty sampled packs by the rule declared in the spec,
renders them in that order from the same campaign record and stored
hypotheses `build_scoring_pack.py` reads, and writes the three files the
second rater is handed to `scoring_pack_rater2/`: `hypotheses.md`,
`score_sheet2.xlsx` and `answer_sheet.md`. No arm key is written there, so the
folder can be handed over whole.

**Every file the first rater scored against or filled in is checksummed
before and after**, and the script fails if any of them moved. Each rendered
pack is also compared with the same pack in the first rater's
`hypotheses.md`: same labels, same text, only the heading's numbering
differs. That is what lets the two sheets join on item id.

The log prints bundle ids, kinds and counts only.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.campaign import generations_from_json
from app.db.bundles import stored_bundles_for_run
from app.db.hypotheses import hypotheses_for_bundle
from app.evaluation.answers import build_answer_sheet, pack_order
from app.evaluation.pack import BLINDING_GIVEAWAYS, DIMENSIONS, JUDGEMENTS, build_pack
from app.evaluation.sampling import SUBSET_QUOTA, SUBSET_SEED, draw_rater_subset
from app.evaluation.workbook import score_sheet_workbook

#: The first rater's label seed, from `build_scoring_pack.py`. Checked below
#: against the first rater's own pack rather than trusted.
SHUFFLE_SEED = 20260929

HERE = Path(__file__).parent
SAMPLE = HERE / "scored_sample.json"
RECORD = HERE / "scored_campaign_record.json"
FIRST = HERE / "scoring_pack"
OUT = HERE / "scoring_pack_rater2"
FIRST_RATER_FILES = (
    "hypotheses.md",
    "answer_sheet.md",
    "score_sheet1.xlsx",
    "score_sheet.csv",
    "arm_key.csv",
    "arm_key.xlsx",
)


def checksums() -> dict[str, str]:
    return {
        name: hashlib.sha256((FIRST / name).read_bytes()).hexdigest()
        for name in FIRST_RATER_FILES
    }


def sections(md: str) -> dict[int, str]:
    """Each pack's body after its heading line, keyed by bundle id."""
    out = {}
    for chunk in md.split("## Evidence pack ")[1:]:
        heading, _, body = chunk.partition("\n")
        body = body.rstrip()
        out[int(heading.split(" ")[0])] = body.removesuffix("---").rstrip()
    return out


def workbook_text(path: Path) -> str:
    """Every word a marker could see in the workbook, including its notes."""
    import openpyxl

    book = openpyxl.load_workbook(path)
    parts = [*book.sheetnames, str(book.properties.creator or "")]
    parts.append(str(book.properties.title or ""))
    for sheet in book:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value is not None:
                    parts.append(str(cell.value))
                if cell.comment is not None:
                    parts.append(str(cell.comment.text))
    return " ".join(parts).lower()


before = checksums()

entries = json.loads(SAMPLE.read_text())["entries"]
kind = {int(e["bundle_id"]): e["kind"] for e in entries}
scenario = {int(e["bundle_id"]): str(e["scenario_type"]) for e in entries}
order = draw_rater_subset(entries, quota=SUBSET_QUOTA, seed=SUBSET_SEED)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

with factory.begin() as session:
    rows = session.execute(
        text(
            "SELECT b.id, b.scenario_run_id, r.ground_truth "
            "FROM evidence_bundles b JOIN scenario_runs r ON r.id = b.scenario_run_id "
            "WHERE b.id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": list(order)},
    ).all()

run_of = {int(bundle_id): int(run_id) for bundle_id, run_id, _ in rows}
truths = {int(b): truth for b, _, truth in rows if truth is not None}
bundles = {
    bundle_id: bundle
    for run_id in sorted(set(run_of.values()))
    for bundle_id, bundle in stored_bundles_for_run(factory, run_id)
    if bundle_id in order
}
generations = [
    g
    for g in generations_from_json(json.loads(RECORD.read_text()))
    if g.bundle_id in order
]
hypotheses = {
    row.id: row.hypothesis
    for bundle_id in order
    for row in hypotheses_for_bundle(factory, bundle_id)
}

pack = build_pack(
    generations=generations,
    bundles=sorted(bundles.items()),
    hypotheses=hypotheses,
    seed=SHUFFLE_SEED,
    order=order,
)

first = sections((FIRST / "hypotheses.md").read_text())
differs = [b for b, body in sections(pack.hypotheses_md).items() if first[b] != body]
if differs:
    raise SystemExit(
        f"pack(s) {differs} render differently from the first rater's copy, "
        "so the two sheets would not join on item id"
    )

sheet = build_answer_sheet(
    order=pack_order(pack.hypotheses_md),
    # The answer sheet answers exactly the packs rendered.
    sample={b: scenario[b] for b in order},
    truths=truths,
    bundles=bundles,
)

OUT.mkdir(exist_ok=True)
(OUT / "hypotheses.md").write_text(pack.hypotheses_md)
(OUT / "score_sheet2.xlsx").write_bytes(score_sheet_workbook(pack.items))
(OUT / "answer_sheet.md").write_text(sheet)

marker_reads = "\n".join(
    [
        pack.hypotheses_md.lower(),
        sheet.lower(),
        workbook_text(OUT / "score_sheet2.xlsx"),
    ]
)
leaks = [w for w in BLINDING_GIVEAWAYS if w in marker_reads]
if leaks:
    raise SystemExit(f"the second rater's files name the arms {leaks}")

after = checksums()
moved = [name for name in FIRST_RATER_FILES if before[name] != after[name]]
if moved:
    raise SystemExit(f"first-rater file(s) {moved} changed")

pass_one = len(pack.items) * len(DIMENSIONS)
pass_two = len(pack.items) * len(JUDGEMENTS)
print(f"sample       {SAMPLE.name}, {len(entries)} bundles")
print(f"draw         seed {SUBSET_SEED}, quota {dict(SUBSET_QUOTA)}")
print("\norder the second rater reads:")
for position, bundle_id in enumerate(order, start=1):
    print(
        f"  {position:2}  {bundle_id:05d}  {kind[bundle_id]:27} {scenario[bundle_id]}"
    )
print(
    f"\npacks        {pack.bundles}, every one byte-identical to the first "
    "rater's apart from its heading"
)
print(f"explanations {len(pack.items)}")
print(f"values       {pass_one} in pass one, {pass_two} in pass two, ")
print(f"             {pass_one + pass_two} in all")
print(
    "             The participant information sheet and the ethics form quote\n"
    "             280. Both live outside this repository and must be updated\n"
    "             by the author to the figure above."
)
print(f"\narm vocabulary in all three files: {leaks or 'none'}")
print("\nfirst rater's files, sha256 before = after:")
for name in FIRST_RATER_FILES:
    print(f"  {name:20} {after[name][:16]}")
print(f"\nwritten to {OUT.name}/: hypotheses.md, score_sheet2.xlsx, answer_sheet.md")
