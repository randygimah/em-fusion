"""What does one evidence bundle cost to send, and what is actually in it?

Two questions `ai-004` cannot be specified without, and both were about to
be answered by guessing.

**What does a campaign cost?** The gate before the model arms asks for a
total spend ceiling and for N generations per bundle per arm. Neither can
be chosen without knowing how large a bundle is, and a bundle's size is not
a design parameter -- it is whatever the detection layer produced. This
measures the real ones.

**What leaves the machine?** `NFR-405` forbids a real aircraft identifier
reaching a hosted provider, and `dal-004` already guarantees that by
pseudonymising at ingest. But "no real identifier" is a narrower claim than
"not re-identifiable", and the difference matters for the OpenSky licence
(DLA section 3(i)) rather than for the code. So this inventories **every
field name a bundle carries**, so the answer is a list rather than a
recollection.

The token figure is an estimate and is labelled as one: the prompt `ai-004`
will actually send does not exist yet, so this measures the bundle's own
JSON as a proxy and states the ratio it assumed. It is the right order of
magnitude for choosing a ceiling, and it is not a billing forecast.

No aircraft identifier is printed, per `measurements/README.md`.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.bundles import bundles_for_run

#: Characters per token. A crude but standard approximation for English
#: prose with JSON punctuation; stated rather than hidden because the
#: figures below are only as good as it is.
CHARS_PER_TOKEN = 4

AIRCRAFT_ID = re.compile(r"AC-[0-9a-fA-F]+")


def redact(value: object) -> str:
    return AIRCRAFT_ID.sub("AC-<redacted>", str(value))


def field_names(node: object, path: str = "", into: Counter | None = None) -> Counter:
    """Every field name in a bundle, as a dotted path, counted."""
    counter = Counter() if into is None else into
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            counter[here] += 1
            field_names(value, here, counter)
    elif isinstance(node, list):
        for value in node:
            field_names(value, f"{path}[]", counter)
    return counter


print(_corpus.describe(), flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

with factory.begin() as s:
    run_ids = [r[0] for r in s.execute(text(
        f"SELECT DISTINCT b.scenario_run_id FROM evidence_bundles b "
        f"JOIN scenario_runs r ON r.id = b.scenario_run_id "
        f"WHERE {_corpus.run_filter('r')} ORDER BY 1")).all()]

bundles = [b for run_id in run_ids for b in bundles_for_run(factory, run_id)]
if not bundles:
    raise SystemExit("no stored bundles. Run corpus/bundle_end_to_end.py first.")

sizes: list[tuple[int, str, int]] = []
fields: Counter = Counter()
for bundle in bundles:
    payload = {
        "anomaly_type": bundle.anomaly_type,
        "rule_id": bundle.rule_id,
        "subject": bundle.subject,
        "time_window": [t.isoformat() for t in bundle.time_window],
        "affected_area": {"lat": bundle.affected_area.lat,
                          "lon": bundle.affected_area.lon},
        "affected_channels": list(bundle.affected_channels),
        "evidence": [
            {"source": i.source, "finding": i.finding, "rule_id": i.rule_id,
             "finding_type": i.finding_type, "data_mode": i.data_mode.value,
             "grounding": i.grounding.value,
             "started_at": i.started_at.isoformat(),
             "ended_at": i.ended_at.isoformat(),
             "refs": list(i.refs), "details": i.details}
            for i in bundle.evidence],
        "known_uncertainties": [
            {"kind": u.kind.value, "subject": u.subject, "statement": u.statement}
            for u in bundle.known_uncertainties],
        "superseded": [
            {"rule_id": c.rule_id, "anomaly_type": c.anomaly_type,
             "claimed_by": c.claimed_by, "reason": c.reason}
            for c in bundle.superseded],
    }
    serialised = json.dumps(payload)
    sizes.append((len(serialised), bundle.anomaly_type, len(bundle.evidence)))
    field_names(payload, into=fields)

sizes.sort()
chars = [c for c, _, _ in sizes]
median = chars[len(chars) // 2]
tokens = [c // CHARS_PER_TOKEN for c in chars]

print()
print("=" * 78)
print("WHAT ONE BUNDLE COSTS TO SEND")
print("=" * 78)
print(f"  bundles measured: {len(bundles)}")
print(f"  characters   min {chars[0]:,}  median {median:,}  max {chars[-1]:,}")
print(f"  ~tokens      min {tokens[0]:,}  median {tokens[len(tokens) // 2]:,}  "
      f"max {tokens[-1]:,}   (at {CHARS_PER_TOKEN} chars/token, ESTIMATE)")
print()
by_kind: dict[str, list[int]] = {}
for size, kind, _ in sizes:
    by_kind.setdefault(kind, []).append(size)
for kind, values in sorted(by_kind.items()):
    values.sort()
    print(f"    {kind:32} n={len(values):2}  median {values[len(values) // 2]:,} chars")
print()
print("  The largest bundle carries "
      f"{max(n for _, _, n in sizes)} evidence items; the smallest "
      f"{min(n for _, _, n in sizes)}.")
print()
print("  WHAT A CAMPAIGN WOULD SEND (input only; output is extra)")
for bundles_scored in (20, 41):
    for generations in (1, 3):
        total = median * bundles_scored * generations // CHARS_PER_TOKEN
        print(f"    {bundles_scored:2} bundles x {generations} generation(s) x 1 arm"
              f"  ~= {total:,} input tokens")
print("  Two model arms double it. Retries add on top, which is the point of a")
print("  call budget rather than a spend estimate.")

print()
print("=" * 78)
print("WHAT IS ACTUALLY IN ONE -- every field name, so NFR-405 is a list")
print("=" * 78)
for name, count in sorted(fields.items()):
    print(f"  {name:46} x{count}")

positional = [n for n in fields if any(
    word in n.lower() for word in ("lat", "lon", "location", "position",
                                   "altitude", "geom"))]
print()
print(f"  fields that could carry a position: {positional}")
print("  affected_area is the RF receiver or zone centre, from the synthetic")
print("  layout in scn-005 -- not an aircraft position. No aircraft position")
print("  reaches a bundle.")

track_fields = sorted({
    n for n in fields if "refs" in n or "details" in n})
print()
print("  what a TRACK citation carries:")
for name in track_fields:
    print(f"    {name}")
