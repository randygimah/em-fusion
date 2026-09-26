"""The first real requests: three bundles, hand-read.

**This script spends money.** It is the only thing in this repository that
makes a real call to a hosted provider, and it is deliberately the last gate
before a campaign rather than part of one. It requires an explicit opt-in so
that running it by accident costs nothing.

Three bundles, not twenty, and the output is printed in full rather than
asserted on. That is the point: a campaign can tell you a hypothesis
validated and was grounded, and it cannot tell you whether the words are any
good. Somebody has to read three and decide.

Four questions it answers that nothing else can.

1. **Does the request shape work at all?** Strict structured outputs, a
   narrowed schema, a dated model, temperature and seed. Any of these can be
   rejected by the provider, and `ai-004` maps a rejected request to a
   configuration error that stops the run rather than falling back -- so a
   failure here is loud and specific, which is exactly what it is for.

2. **Which schema keywords does strict mode actually accept?** The list this
   package removes is taken from provider documentation and cannot be derived
   locally. What is removed is printed, so the assumption is visible next to
   the result rather than buried in a constant.

3. **Is the cost estimate close?** The figure printed here is computed from
   the prices configured, not billed. Compare it against the provider's own
   usage page afterwards: that comparison is what makes `eval-005`'s reported
   cost credible, and it can only be made now, while three calls are the
   whole of the account's history.

4. **Does the grounding check flag anything?** On a real model rather than on
   a corruption built for the purpose. A catch here is a finding either way --
   the safeguard earning its place, or a prompt that needs a word changing
   before twenty bundles are run through it.

Aircraft identifiers are redacted from everything printed, per
`measurements/README.md`. NFR-405 also applies to what is *sent*: the payload
is `ai-004`'s, which excludes the bundle's run id and each item's row ids, and
pseudonyms are `dal-004`'s rather than real identifiers.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.assembly import ArmPrices, assemble_arm
from app.ai.budget import CallBudget
from app.ai.grounding import GroundingLedger, check
from app.ai.prompt import prompt_fingerprint
from app.ai.providers.openai import API_KEY_VARIABLE, strict_schema
from app.ai.service import GeneratorKind
from app.db.bundles import bundles_for_run

#: Chosen 2026-09-25. A conventional chat model, so temperature and seed are
#: honoured rather than ignored, and strict structured outputs are supported
#: -- the two properties the reproducibility argument rests on. Dated, so it
#: cannot change under the campaign.
MODEL_ID = "gpt-4.1-2025-04-14"

#: Per *1k* tokens. The provider's price list quotes per 1M: $2.00 and $8.00.
PRICES = ArmPrices(usd_per_1k_prompt=0.002, usd_per_1k_completion=0.008)

#: Frozen for the campaign and recorded verbatim beside every hypothesis.
PARAMETERS = {"temperature": 0.0, "seed": 20260925, "max_tokens": 1500}

BUNDLES = 3
#: Three bundles at `ai-007`'s recommended two attempts, and not one more.
MAX_CALLS = BUNDLES * 2
#: A tripwire rather than the guard. Three bundles cost about $0.03.
MAX_COST_USD = 0.25

#: Running this costs money, so it cannot happen by accident.
CONFIRM_VAR = "SMOKE_TEST_CONFIRM"

AIRCRAFT_ID = re.compile(r"AC-[0-9a-fA-F]+")


def redact(value: object) -> str:
    """Anything printed goes through here. No aircraft identifier, ever."""
    return AIRCRAFT_ID.sub("AC-<redacted>", str(value))


def load_credential() -> None:
    """Make the key readable, from the environment or from `backend/.env`.

    The same shape as `app.dal.pseudonymise.load_seed_environment`, and for
    the same reason its docstring records: Compose passes a variable through
    from the host, so an unset one arrives inside a container as an **empty
    string rather than as absent**, and `load_dotenv(override=False)` treats
    present-but-empty as present -- which would let nothing shadow a
    perfectly good `.env`. An empty key is not a key, so it is cleared
    before the file is read.

    Copied rather than shared, deliberately and with the debt recorded: that
    function is seed-specific, and generalising a module in `app/dal/` for
    the AI layer's benefit needs a spec item rather than a measurement
    script's convenience. Its own docstring warns that a remedy copied twice
    is one the third caller will not know about -- so when a campaign runner
    lands in `app/`, this is the moment to generalise rather than copy again.
    """
    if not os.environ.get(API_KEY_VARIABLE, "").strip():
        os.environ.pop(API_KEY_VARIABLE, None)
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.is_file():
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)


if os.environ.get(CONFIRM_VAR, "").strip().lower() not in {"yes", "1", "true"}:
    raise SystemExit(
        f"This script makes real, billed requests to a hosted provider.\n"
        f"Set {CONFIRM_VAR}=yes to run it:\n\n"
        f"    make measure SCRIPT=corpus/hosted_smoke_test.py CORPUS=dev \\\n"
        f"        SMOKE_TEST_CONFIRM=yes\n\n"
        f"Model: {MODEL_ID}   ceiling: {MAX_CALLS} calls / ${MAX_COST_USD}"
    )

load_credential()
if not os.environ.get(API_KEY_VARIABLE, "").strip():
    raise SystemExit(
        f"{API_KEY_VARIABLE} is not set and backend/.env does not supply it. "
        "The credential is read from the environment and never from a "
        "configuration, because generation parameters are persisted verbatim "
        "beside every hypothesis."
    )

print(_corpus.describe(), flush=True)
print(f"model      {MODEL_ID}")
print(f"parameters {PARAMETERS}")
print(f"prompt     sha256 {prompt_fingerprint()}")
print(f"ceiling    {MAX_CALLS} calls, ${MAX_COST_USD} spend\n", flush=True)

schema, removed = strict_schema()
print("=" * 78)
print("WHAT STRICT MODE IS NOT GIVEN")
print("=" * 78)
print(f"  keywords removed from the schema: {list(removed)}")
print("  ai-001's at-least-one-citation and no-blank-summary guarantees are")
print("  therefore enforced at parse time, as a refusal, and not at generation")
print("  time as an impossibility. A malformed refusal below is ordinary if it")
print("  names an empty list, and alarming if it names the confidence enum.\n")

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

available = [b for run_id in run_ids for b in bundles_for_run(factory, run_id)]
if len(available) < BUNDLES:
    raise SystemExit(
        f"only {len(available)} stored bundles for this corpus; "
        "run corpus/bundle_end_to_end.py first."
    )


def choose(pool):
    """One bundle of each shape, then the largest, in bundle order.

    The first three bundles in this corpus are all `possible_sensor_fault`,
    so taking the head exercised one shape twice and the other never -- and
    the shape it missed is the interesting one: an interference bundle spans
    both data modes, carries a track side, and holds 17-23 evidence items
    against a fault bundle's 4-10. Three calls only buy coverage if they are
    chosen rather than taken.

    The largest is included deliberately as the worst case for payload size
    and for how long a citation list a generator will produce.
    """
    chosen, seen = [], set()
    for bundle in pool:
        if bundle.anomaly_type not in seen:
            seen.add(bundle.anomaly_type)
            chosen.append(bundle)
    biggest = max(pool, key=lambda b: len(b.evidence))
    if biggest not in chosen:
        chosen.append(biggest)
    # Pad to the full BUNDLES. The first version stopped here and chose two,
    # because the first interference bundle in this corpus happens also to be
    # the largest, so "plus the biggest" added nothing and a third of the
    # budget went unspent. A trial that silently buys less coverage than it
    # was configured for is the quiet kind of wrong.
    for bundle in pool:
        if len(chosen) >= BUNDLES:
            break
        if bundle not in chosen:
            chosen.append(bundle)
    return chosen[:BUNDLES]


bundles = choose(available)
print(
    f"chose {len(bundles)} of {len(available)}: "
    + ", ".join(f"{b.anomaly_type} ({len(b.evidence)} items)" for b in bundles)
    + "\n",
    flush=True,
)

budget = CallBudget(max_calls=MAX_CALLS, max_cost_usd=MAX_COST_USD)
ledger = GroundingLedger()
arm = assemble_arm(
    arm=GeneratorKind.HOSTED,
    provider="openai",
    model_id=MODEL_ID,
    parameters=PARAMETERS,
    budget=budget,
    ledger=ledger,
    max_attempts=2,
    prices=PRICES,
)

for n, bundle in enumerate(bundles, start=1):
    print("=" * 78)
    print(f"{n}. {bundle.anomaly_type.upper()} on {redact(bundle.subject)}")
    print("=" * 78, flush=True)

    outcome = arm.generator.generate_recorded(bundle)
    h = outcome.result.hypothesis

    for refusal in outcome.refusals:
        print(
            f"  REFUSED attempt {refusal.attempt} ({refusal.category.value}): "
            f"{redact(refusal.reason)}\n"
        )
    if outcome.fell_back:
        print(
            "  *** FELL BACK TO THE TEMPLATE -- the model's answer was not "
            "usable ***\n"
        )

    print(f"  title       {redact(h.hypothesis_title)}")
    print(f"  confidence  {h.confidence.value}")
    print(f"  summary     {redact(h.summary)}\n")
    print("  supporting evidence:")
    for c in h.supporting_evidence:
        print(f"    - {c.rule_id}/{c.finding_type}: {redact(c.statement)}")
    print("\n  alternatives:")
    for a in h.alternative_explanations:
        print(f"    - {redact(a)}")
    print("\n  against / uncertain:")
    for a in h.evidence_against_or_uncertainty:
        print(f"    - {redact(a)}")
    print(f"\n  recommended action: {redact(h.recommended_human_action)}")

    report = check(h, bundle)
    print(
        f"\n  grounding: {'PASS' if report.passed else 'FAIL'}"
        f"   {len(report.findings)} citations"
    )
    for finding in report.ungrounded:
        print(
            f"    - {redact(finding.rule_id)}/{redact(finding.finding_type)}: "
            f"{redact(finding.detail)}"
        )
    if outcome.result.call is not None:
        u = outcome.result.call.usage
        priced = f"   estimated ${u.cost_usd:.4f}" if u.cost_usd is not None else ""
        print(f"  tokens: {u.prompt_tokens} in, {u.completion_tokens} out{priced}")
    print(flush=True)

report = budget.report()
print("=" * 78)
print("WHAT IT COST")
print("=" * 78)
print(f"  calls              {report.call_count} of {MAX_CALLS}")
print(f"  prompt tokens      {report.prompt_tokens}")
print(f"  completion tokens  {report.completion_tokens}")
print(f"  estimated spend    ${report.spent_usd:.4f}")
print(f"  unpriced calls     {report.unpriced_calls}")
print(f"  total is complete  {report.cost_is_complete}")
print("  Compare the estimate against the provider's own usage page. That")
print("  comparison is what makes eval-005's reported cost credible, and it")
print("  can only be made now, while three calls are the account's whole")
print("  history.\n")

print("=" * 78)
print("WHAT THE SAFEGUARD SAID")
print("=" * 78)
rate = ledger.catch_rate(GeneratorKind.HOSTED)
print(f"  hypotheses checked {ledger.checked(GeneratorKind.HOSTED)}")
print(f"  caught             {ledger.caught(GeneratorKind.HOSTED)}")
print(f"  catch rate         {rate}")
near = ledger.near_misses(GeneratorKind.HOSTED)
print(f"  near misses        {[f.near_miss.value for f in near]}")
print("\n  A catch here is a finding either way: the safeguard earning its")
print("  place, or a prompt that needs a word changed before twenty bundles")
print("  are run through it.")

sys.stdout.flush()
