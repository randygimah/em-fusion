"""Does the grounding check work on the bundles the system really makes?

`ai-008` is the safeguard everything after it trusts, so "it passes its
unit tests" is a weaker claim here than anywhere else in the project. This
asks the two questions a safeguard has to answer, over the **stored**
bundles -- written to the database by `bundle_end_to_end.py` through the
shipped resolver, from detection over real replayed hours, and the exact
objects the AI layer will be handed.

1. **Does it flag anything it should not?** The template generator copies
   every word it writes out of the bundle, so a template hypothesis is
   grounded by construction. That makes it an input whose correct answer is
   known in advance: **anything flagged here is a defect in the check**,
   not in the generator. This is the cheap validation `docs/phase9` builds
   the ordering around, and it is the whole reason `ai-008` comes after
   `ai-002` rather than before it.

   It is a different question from the one `template_hypotheses.py` asks in
   its section 2. That script resolves citations with a hand-written loop
   and is testing the *template*. This runs the shipped module and is
   testing the *check* -- which is also why the two must not share their
   derivation of the citation key, and why a test walks the import graph to
   hold that.

2. **Does it catch what it should?** Specificity without sensitivity is a
   check that returns "fine" and passes question 1 perfectly. So every real
   hypothesis is also corrupted four ways, one citation at a time, and each
   corruption must be caught. No model is called and no model error is
   simulated beyond the identifier: these are template hypotheses with one
   citation rewritten, standing in for the four things a model can get
   wrong about an identifier it was shown.

The fifth corruption -- citing a claim the ladder rejected -- **cannot be
exercised on this corpus**, and that is recorded rather than worked around.
`ladder_suppression.log` measured 188 claims bid and 0 suppressed across
corpus v2, so no bundle here carries a superseded field at all. The check's
superseded verdict is proved by unit tests over constructed bundles, and a
corpus demonstration is owed to a second producing rule alongside
`anom-013`'s arbitration. This script counts the superseded fields it finds
so that the day one appears, the figure moves on its own.

Aircraft identifiers are redacted from everything printed, per
`measurements/README.md`.
"""

from __future__ import annotations

import os
import re
from collections import Counter

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.grounding import CitationVerdict, GroundingChecker, GroundingLedger
from app.ai.hypothesis import Citation, Hypothesis
from app.ai.service import GeneratorKind
from app.ai.template import TemplateError, generate
from app.db.bundles import bundles_for_run

AIRCRAFT_ID = re.compile(r"AC-[0-9a-fA-F]+")


def redact(value: object) -> str:
    """Anything printed goes through here. No aircraft identifier, ever."""
    return AIRCRAFT_ID.sub("AC-<redacted>", str(value))


def recite(hypothesis: Hypothesis, rule_id: str, finding_type: str) -> Hypothesis:
    """The same hypothesis with its first citation replaced."""
    first = hypothesis.supporting_evidence[0]
    swapped = Citation(
        rule_id=rule_id, finding_type=finding_type, statement=first.statement
    )
    return Hypothesis(
        **{
            **hypothesis.model_dump(),
            "supporting_evidence": (swapped, *hypothesis.supporting_evidence[1:]),
        }
    )


print(_corpus.describe(), flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

with factory.begin() as s:
    run_ids = [
        r[0]
        for r in s.execute(
            text(
                f"SELECT DISTINCT b.scenario_run_id FROM evidence_bundles b "
                f"JOIN scenario_runs r ON r.id = b.scenario_run_id "
                f"WHERE {_corpus.run_filter('r')} ORDER BY 1"
            )
        ).all()
    ]

bundles = [b for run_id in run_ids for b in bundles_for_run(factory, run_id)]
print(f"{len(bundles)} stored bundles from {len(run_ids)} runs\n", flush=True)
if not bundles:
    raise SystemExit(
        "no stored bundles for this corpus. Run corpus/bundle_end_to_end.py "
        "first -- it is what writes them."
    )

# ------------------------------------------------------------ 1. specificity

honest = GroundingLedger()
honest_check = GroundingChecker(arm=GeneratorKind.TEMPLATE, ledger=honest)

refused: list[str] = []
false_catches: list[str] = []
citations_checked = 0
carrying_superseded = 0
sample_reason = ""

pairs: list[tuple[Hypothesis, object]] = []
for bundle in bundles:
    if bundle.superseded:
        carrying_superseded += 1
    try:
        hypothesis = generate(bundle)
    except TemplateError as error:
        refused.append(f"run {bundle.scenario_run_id} {bundle.rule_id}: {error}")
        continue
    pairs.append((hypothesis, bundle))

    report = honest_check.report(hypothesis, bundle)
    citations_checked += len(report.findings)
    if not report.passed:
        false_catches.append(f"run {bundle.scenario_run_id}: {report.reason}")

# ------------------------------------------------------------ 2. sensitivity

corrupted = GroundingLedger()
corrupt_check = GroundingChecker(arm=GeneratorKind.HOSTED, ledger=corrupted)

CORRUPTIONS = (
    "an invented rule id",
    "a real rule cited under a finding type it did not produce",
    "a real pair with the case flipped",
    "the bundle's own claim cited as evidence for itself",
)
missed: list[str] = []
caught_by: Counter[str] = Counter()
verdicts: Counter[str] = Counter()
near_misses: Counter[str] = Counter()

for hypothesis, bundle in pairs:
    real = hypothesis.supporting_evidence[0]
    variants = (
        recite(hypothesis, "RF-NOISE-999", real.finding_type),
        recite(hypothesis, real.rule_id, "a_finding_type_nobody_emits"),
        recite(hypothesis, real.rule_id.lower(), real.finding_type.upper()),
        recite(hypothesis, bundle.rule_id, "the_claim_itself"),
    )
    for name, variant in zip(CORRUPTIONS, variants):
        report = corrupt_check.report(variant, bundle)
        if report.passed:
            missed.append(f"run {bundle.scenario_run_id}: {name} was not caught")
            continue
        caught_by[name] += 1
        finding = report.findings[0]
        verdicts[finding.verdict.value] += 1
        near_misses[finding.near_miss.value if finding.near_miss else "none"] += 1
        if not sample_reason:
            sample_reason = report.reason

# --------------------------------------------------------------- the report

print("=" * 78)
print("1. WHAT IT FLAGS ON INPUT WHOSE ANSWER IS KNOWN")
print("=" * 78)
print(f"  template hypotheses generated: {len(pairs)} of {len(bundles)} bundles")
for line in refused:
    print(f"    {redact(line)}")
print(f"  citations resolved against their own bundle: {citations_checked}")
print(
    f"  flagged: {len(false_catches)}"
    f"{'   PASS' if not false_catches else '   *** DEFECT IN THE CHECK ***'}"
)
for line in false_catches:
    print(f"    {redact(line)}")
rate = honest.catch_rate(GeneratorKind.TEMPLATE)
print(
    f"  catch rate on the template arm: {rate}"
    "   (0.0 is measured; None would mean nothing ran)"
)

print()
print("=" * 78)
print("2. WHAT IT CATCHES WHEN ONE CITATION IS CORRUPTED")
print("=" * 78)
print(
    f"  hypotheses corrupted: {len(pairs)} x {len(CORRUPTIONS)} "
    f"= {len(pairs) * len(CORRUPTIONS)}"
)
for name in CORRUPTIONS:
    print(f"    {name:56} caught {caught_by[name]:3} of {len(pairs)}")
print(f"  missed: {len(missed)}" f"{'   PASS' if not missed else '   *** FAIL ***'}")
for line in missed:
    print(f"    {redact(line)}")
print(
    f"  catch rate on the corrupted set: {corrupted.catch_rate(GeneratorKind.HOSTED)}"
)
print(f"  verdicts: {dict(verdicts)}")
print(f"  near misses: {dict(near_misses)}")
print(
    f"  near misses recorded on the arm: "
    f"{len(corrupted.near_misses(GeneratorKind.HOSTED))}"
)

print()
print("=" * 78)
print("3. THE CASE THIS CORPUS CANNOT EXERCISE")
print("=" * 78)
print(f"  bundles carrying a superseded claim: {carrying_superseded} of {len(bundles)}")
print(
    "  anom-013 suppressed 0 of 188 claims across this corpus "
    "(ladder_suppression.log),"
)
print("  so the superseded verdict is proved by unit tests over constructed")
print("  bundles and a corpus demonstration is owed to a second producing rule.")

print()
print("=" * 78)
print("4. WHAT AN INVESTIGATOR IS HANDED")
print("=" * 78)
print(f"  {redact(sample_reason)}")
