"""Copy the committed campaign record's positions into the store. Spec: db-012.

**Writes the store, and only with confirmation.** Without it the script reports
what it would do and writes nothing:

    make measure SCRIPT=corpus/backfill_campaign_ordinal.py                      # scope only
    make measure SCRIPT=corpus/backfill_campaign_ordinal.py ORDINAL_CONFIRM=yes  # and write

The record is the authority: each generation's ordinal is copied onto the row it
names, in one transaction, by `record_campaign_ordinals`, which refuses the whole
copy if any row disagrees with the record. Rows the record does not name -- the
trial requests made before the campaign -- keep no position. Running it twice
changes nothing.

Prints counts only. No aircraft identifier and no hypothesis text reaches this log.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.campaign import generations_from_json
from app.db.hypotheses import record_campaign_ordinals

CONFIRM_VAR = "ORDINAL_CONFIRM"
RECORD = Path(__file__).with_name("scored_campaign_record.json")


def confirmed() -> bool:
    return os.environ.get(CONFIRM_VAR, "").strip().lower() in {"yes", "1", "true"}


def stored_positions(factory: sessionmaker) -> Counter[str]:
    with factory.begin() as session:
        rows = session.execute(
            text(
                "SELECT requested_generator, campaign_ordinal IS NULL AS blank "
                "FROM hypotheses"
            )
        ).all()
    return Counter(
        f"{arm:8} {'no position' if blank else 'position'}" for arm, blank in rows
    )


engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
generations = [
    g
    for g in generations_from_json(json.loads(RECORD.read_text()))
    if g.hypothesis_id is not None
]

print(f"record     {RECORD.name}, {len(generations)} stored generations")
print(f"           {dict(sorted(Counter(g.ordinal for g in generations).items()))} by ordinal")
print("\nstore before:")
for key, n in sorted(stored_positions(factory).items()):
    print(f"  {key}  {n}")

if not confirmed():
    print(f"\n{CONFIRM_VAR} is not set: nothing written.")
    raise SystemExit(0)

outcome = record_campaign_ordinals(factory, generations)
print(f"\nwritten    {outcome.written}")
print(f"unchanged  {outcome.unchanged}")
print("\nstore after:")
for key, n in sorted(stored_positions(factory).items()):
    print(f"  {key}  {n}")
