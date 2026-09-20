"""Does the template generator work on the bundles the system really makes?

Everything proving `ai-002` so far is a unit test over bundles this
project's own fixtures constructed. That is better than hand-written
`EvidenceBundle` literals -- the fixtures drive the real builder -- but it
is still a closed loop: the bundles were built from findings I chose, over
receivers I named, in windows I set.

This reads the **stored** bundles instead. They were written to the
database by `bundle_end_to_end.py` through the shipped resolver, from
detection over real replayed hours, and they are the exact objects the AI
layer will be handed. Three questions are asked of them.

1. **Does it refuse anything?** Every refusal this generator has is a
   bundle that would force an invention -- no verdict, two verdicts, a
   confidence that is missing or is not a word. All of those are
   unreachable in the unit tests except by deliberately damaging a bundle.
   A refusal here would mean a bundle shape the item did not anticipate,
   and it would mean the *correctness fallback* failing on real input,
   which is the worst place for it.

2. **Is it grounded by construction, in fact and not only by argument?**
   Every citation's `(rule_id, finding_type)` pair is looked up in the
   bundle it came from. This is `ai-008`'s question asked of the one
   generator whose answer is supposed to be yes by construction, which is
   what makes the template a test of the grounding check later rather than
   the other way round.

3. **Is it deterministic across processes?** The campaign compares arms
   over identical bundles, so a baseline that varied would make a
   difference in scores unattributable to the generator. Each bundle is
   generated twice and the JSON compared, and the whole script is run
   under a fixed hash seed by the harness the README documents.

Then one complete hypothesis is printed, so what a scorer will read can be
read rather than described. Aircraft identifiers are redacted from
everything printed, per `measurements/README.md`: they are already
`dal-004` pseudonyms, and the rule is that no aircraft identifier of any
kind reaches a committed log.
"""
from __future__ import annotations

import os
import re
from collections import Counter

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.template import TemplateError, generate
from app.db.bundles import bundles_for_run

AIRCRAFT_ID = re.compile(r"AC-[0-9a-fA-F]+")


def redact(value: object) -> str:
    """Anything printed goes through here. No aircraft identifier, ever."""
    return AIRCRAFT_ID.sub("AC-<redacted>", str(value))


print(_corpus.describe(), flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

with factory.begin() as s:
    run_ids = [r[0] for r in s.execute(text(
        f"SELECT DISTINCT b.scenario_run_id FROM evidence_bundles b "
        f"JOIN scenario_runs r ON r.id = b.scenario_run_id "
        f"WHERE {_corpus.run_filter('r')} ORDER BY 1")).all()]

bundles = [b for run_id in run_ids for b in bundles_for_run(factory, run_id)]
print(f"{len(bundles)} stored bundles from {len(run_ids)} runs\n", flush=True)
if not bundles:
    raise SystemExit(
        "no stored bundles for this corpus. Run corpus/bundle_end_to_end.py "
        "first -- it is what writes them."
    )

refused: list[str] = []
ungrounded: list[str] = []
unstable: list[str] = []
confidences: Counter[str] = Counter()
by_type: Counter[str] = Counter()
citations: list[int] = []
alternatives: list[int] = []
against: list[int] = []
sample = None

for bundle in bundles:
    try:
        hypothesis = generate(bundle)
    except TemplateError as error:
        refused.append(f"run {bundle.scenario_run_id} {bundle.rule_id}: {error}")
        continue

    # 2 -- every citation names a kind of evidence this bundle carries.
    available = {(i.rule_id, i.finding_type) for i in bundle.evidence}
    for citation in hypothesis.supporting_evidence:
        if (citation.rule_id, citation.finding_type) not in available:
            ungrounded.append(
                f"run {bundle.scenario_run_id}: cites "
                f"{citation.rule_id}/{citation.finding_type}, absent from the bundle")

    # 3 -- same bundle, same words.
    if generate(bundle).model_dump_json() != hypothesis.model_dump_json():
        unstable.append(f"run {bundle.scenario_run_id} {bundle.rule_id}")

    confidences[hypothesis.confidence.value] += 1
    by_type[bundle.anomaly_type] += 1
    citations.append(len(hypothesis.supporting_evidence))
    alternatives.append(len(hypothesis.alternative_explanations))
    against.append(len(hypothesis.evidence_against_or_uncertainty))
    if sample is None and bundle.anomaly_type == "possible_interference_zone":
        sample = (bundle, hypothesis)


def spread(name: str, values: list[int]) -> str:
    ordered = sorted(values)
    median = ordered[len(ordered) // 2]
    return (f"  {name:24} min {ordered[0]}  median {median}  "
            f"max {ordered[-1]}  total {sum(ordered)}")


print("=" * 78)
print("WHAT IT PRODUCED")
print("=" * 78)
print(f"  hypotheses generated: {len(citations)} of {len(bundles)} bundles")
print(f"  refused: {len(refused)}"
      f"{'   PASS' if not refused else '   *** SEE BELOW ***'}")
for line in refused:
    print(f"    {redact(line)}")
print(f"  by kind of claim: {dict(by_type)}")
print(f"  confidence, inherited from the deciding rule: {dict(confidences)}")
print(spread("citations", citations))
print(spread("alternatives", alternatives))
print(spread("uncertainties carried", against))

print()
print("=" * 78)
print("GROUNDED BY CONSTRUCTION, CHECKED RATHER THAN ARGUED")
print("=" * 78)
print(f"  citations checked against their own bundle: {sum(citations)}")
print(f"  citing something the bundle does not carry: {len(ungrounded)}"
      f"{'   PASS' if not ungrounded else '   *** FAIL ***'}")
for line in ungrounded:
    print(f"    {redact(line)}")
print(f"  bundles generating different words on a second run: {len(unstable)}"
      f"{'   PASS' if not unstable else '   *** FAIL ***'}")
for line in unstable:
    print(f"    {redact(line)}")

if sample is not None:
    bundle, hypothesis = sample
    print()
    print("=" * 78)
    print("ONE HYPOTHESIS, AS A BLIND SCORER WOULD READ IT")
    print("=" * 78)
    print(f"  run {bundle.scenario_run_id}, from a bundle of "
          f"{len(bundle.evidence)} evidence items")
    print()
    print(f"  TITLE       {redact(hypothesis.hypothesis_title)}")
    print(f"  CONFIDENCE  {hypothesis.confidence.value}")
    print(f"  SUMMARY     {redact(hypothesis.summary)}")
    print()
    print(f"  SUPPORTING EVIDENCE ({len(hypothesis.supporting_evidence)} citations)")
    for citation in hypothesis.supporting_evidence:
        print(f"    [{citation.rule_id} / {citation.finding_type}]")
        print(f"      {redact(citation.statement)}")
    print()
    print(f"  EVIDENCE AGAINST / UNCERTAINTY "
          f"({len(hypothesis.evidence_against_or_uncertainty)})")
    for line in hypothesis.evidence_against_or_uncertainty:
        print(f"    - {redact(line)}")
    print()
    print(f"  ALTERNATIVE EXPLANATIONS "
          f"({len(hypothesis.alternative_explanations)})")
    for line in hypothesis.alternative_explanations:
        print(f"    - {redact(line)}")
    print()
    print(f"  RECOMMENDED HUMAN ACTION")
    print(f"    {redact(hypothesis.recommended_human_action)}")
