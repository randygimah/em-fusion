"""The scored campaign: twenty packages, both arms, every answer kept. Spec: ai-012.

**This script spends money.** It is the second of the two real-billing
scripts in this repository, after `hosted_smoke_test.py`, and it requires an
explicit opt-in so that running it by accident costs nothing.

**It cannot draw its own sample.** The twenty come from `scored_sample.json`,
written by `draw_scored_sample.py` and committed before this is run -- and if
that file is missing this refuses rather than helpfully drawing one. A runner
able to choose its own packages could choose them after seeing how the first
few turned out, which is what `docs/scoring_rubric.md`'s pre-registration
exists to rule out and what `ai-012` refuses for the same reason one layer
down.

**Three generations per bundle from the model arm, one from the baseline.**
The first model generation is what `eval-004` scores and is never
substituted, including when it fell back; the other two are `eval-005`'s
grounding-variance population. N was raised from 1 on 2026-09-27 because the
premise behind 1 -- that temperature 0 with a fixed seed returns the
identical answer -- was measured false by the three-bundle trial. The change
is argued in the rubric's change log rather than made here.

What it writes: `scored_campaign_record.json`, the account `eval-005` reports
from and `eval-004`'s export reads to find each bundle's scored generation.
Aircraft identifiers are redacted from everything printed, per
`measurements/README.md`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import _corpus
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.assembly import ArmPrices, assemble_arm
from app.ai.budget import CallBudget
from app.ai.campaign import CampaignAborted, run_campaign
from app.ai.grounding import GroundingLedger
from app.ai.prompt import prompt_fingerprint
from app.ai.providers.openai import API_KEY_VARIABLE
from app.ai.registry import build_generator
from app.ai.service import GenerationConfig, GeneratorKind
from app.db.bundles import stored_bundles_for_run
from app.db.migrations import alembic_config

#: The same model, prices and parameters the trial ran against. Repeated here
#: rather than imported from the smoke test: these are campaign facts
#: persisted verbatim beside every hypothesis, and a change to the pre-flight
#: script must not silently change what the campaign recorded itself as.
MODEL_ID = "gpt-4.1-2025-04-14"
PRICES = ArmPrices(usd_per_1k_prompt=0.002, usd_per_1k_completion=0.008)
PARAMETERS = {"temperature": 0.0, "seed": 20260925, "max_tokens": 1500}

#: eval-004, as amended 2026-09-27. The first is scored; the other two are
#: never scored and become eval-005's variance population.
GENERATIONS = 3
#: ai-007's recommended ceiling, now supported by measurement rather than by
#: asymmetric arithmetic: the provider is not deterministic, so a retry has a
#: genuine chance of a different answer.
MAX_ATTEMPTS = 2

#: Seconds between model calls, **measured rather than guessed**. The first
#: run of this script made 60 calls as fast as it could against the account's
#: 30,000 tokens-per-minute ceiling and the provider refused five of them --
#: two of which were generation 1, so two of twenty bundles came out with no
#: scored generation and the marking corpus silently went from 20 to 18.
#: Prompts measured at 294,527 tokens over 60 calls, so 4,909 each: 30,000 /
#: 4,909 is 6.1 calls a minute, or 9.8 seconds apart. 11 for margin, which
#: puts a 60-call run at about 11 minutes.
PAUSE_SECONDS = 11.0

#: 20 bundles x 3 generations x 2 attempts is 120 at the absolute worst, so
#: ai-009's recommended 200 leaves headroom without leaving a loop unbounded.
MAX_CALLS = 200
#: A tripwire and not the guard -- it fires one call late by construction.
#: The campaign is estimated at about $0.97 before the ~19% the estimate has
#: been running high.
MAX_COST_USD = 3.00

CONFIRM_VAR = "CAMPAIGN_CONFIRM"

SAMPLE = Path(__file__).with_name("scored_sample.json")
OUT = Path(__file__).with_name("scored_campaign_record.json")

AIRCRAFT_ID = re.compile(r"AC-[0-9a-fA-F]+")


def redact(value: object) -> str:
    """Anything printed goes through here. No aircraft identifier, ever."""
    return AIRCRAFT_ID.sub("AC-<redacted>", str(value))


def load_credential() -> None:
    """Make the key readable, from the environment or from `backend/.env`.

    The same shape as `hosted_smoke_test.load_credential` and
    `app.dal.pseudonymise.load_seed_environment`, and for the reason their
    docstrings record: Compose passes a variable through from the host, so an
    unset one arrives inside a container as an **empty string rather than as
    absent**, and `load_dotenv(override=False)` treats present-but-empty as
    present -- which would let nothing shadow a perfectly good `.env`.

    **This is the third copy, and the debt is now due.** That module's own
    note warns a remedy copied twice is one the third caller will not know
    about. Generalising it needs a spec item rather than another script's
    convenience, and it is recorded in `docs/handoff.md` as owed.
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
        f"    make measure SCRIPT=corpus/scored_campaign.py CORPUS=dev \\\n"
        f"        CAMPAIGN_CONFIRM=yes\n\n"
        f"Model: {MODEL_ID}   ceiling: {MAX_CALLS} calls / ${MAX_COST_USD}\n"
        f"Estimated: about $0.97 over 20 bundles x {GENERATIONS} generations."
    )

if not SAMPLE.is_file():
    raise SystemExit(
        f"{SAMPLE.name} does not exist. The corpus is fixed and committed "
        "before the campaign runs, so this refuses to draw one rather than "
        "helpfully inventing it:\n\n"
        "    make measure SCRIPT=corpus/draw_scored_sample.py CORPUS=dev\n\n"
        "then commit the file it writes."
    )

load_credential()
if not os.environ.get(API_KEY_VARIABLE, "").strip():
    raise SystemExit(
        f"{API_KEY_VARIABLE} is not set and backend/.env does not supply it. "
        "The credential is read from the environment and never from a "
        "configuration, because generation parameters are persisted verbatim "
        "beside every hypothesis."
    )

drawn = json.loads(SAMPLE.read_text())
wanted = [entry["bundle_id"] for entry in drawn["entries"]]

print(_corpus.describe())
print(f"model      {MODEL_ID}")
print(f"parameters {PARAMETERS}")
print(f"prompt     sha256 {prompt_fingerprint()}")
print(f"sample     {SAMPLE.name}, seed {drawn['seed']}, {len(wanted)} bundles")
print(f"ceiling    {MAX_CALLS} calls, ${MAX_COST_USD} spend")
print(f"generations {GENERATIONS} from the model arm, 1 from the baseline")
print(f"pacing     {PAUSE_SECONDS}s between model calls\n", flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

# --- the schema, checked BEFORE the first billed call ------------------------
#
# Added after this script spent a real request and then failed to store the
# answer: the application database was two revisions behind, because the test
# fixtures migrate the *test* database and nothing migrates this one on the
# way in. The write is the last thing that happens to a generation, so a
# schema gap costs a paid call per bundle and stores none of them -- the one
# shape of failure this script's other refusals all exist to prevent, arriving
# through the one door that had no check on it.
#
# Every other precondition here is checked before the credential is even read.
# This one has to wait for a connection, so it is the first thing done with one.
with engine.connect() as connection:
    at = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
head = ScriptDirectory.from_config(alembic_config()).get_current_head()
if at != head:
    raise SystemExit(
        f"the database is at revision {at!r} and the code expects {head!r}. "
        "A generation is written after it is paid for, so running now would "
        "spend a request per bundle and store none of them. Bring it up "
        "first:\n\n    make migrate\n"
    )
print(f"schema     {head} (checked before anything is asked)\n", flush=True)

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
missing = [bundle_id for bundle_id in wanted if bundle_id not in held]
if missing:
    raise SystemExit(
        f"the committed sample names {len(missing)} bundle(s) this corpus does "
        f"not hold: {missing}. The bundles were regenerated after the sample "
        "was drawn, so the pre-registered corpus no longer exists and the "
        "sample has to be drawn again -- which is a change to the "
        "pre-registration and belongs in the rubric's change log."
    )

# In the sample's own order, which is fixed and recorded. Rebuilt from the
# committed ids rather than taken from the store's order, so the campaign
# asks about exactly what was pre-registered, in exactly that order.
sample = [(bundle_id, held[bundle_id]) for bundle_id in wanted]

budget = CallBudget(max_calls=MAX_CALLS, max_cost_usd=MAX_COST_USD)
ledger = GroundingLedger()
arm = assemble_arm(
    arm=GeneratorKind.HOSTED,
    provider="openai",
    model_id=MODEL_ID,
    parameters=PARAMETERS,
    budget=budget,
    ledger=ledger,
    max_attempts=MAX_ATTEMPTS,
    prices=PRICES,
)
baseline = build_generator(GenerationConfig(provider="template", model_id=None))

try:
    record = run_campaign(
        factory,
        sample=sample,
        arm=arm,
        baseline=baseline,
        generations=GENERATIONS,
        pause_seconds=PAUSE_SECONDS,
    )
    aborted = None
except CampaignAborted as stopped:
    record, aborted = stopped.record, stopped

OUT.write_text(json.dumps(record.as_json(), indent=2, sort_keys=True) + "\n")

print("=" * 78)
print("WHAT RAN")
print("=" * 78)
for generation in record.generations:
    mark = "  <- FELL BACK" if generation.fell_back else ""
    print(
        f"  bundle {generation.bundle_id:>6}  "
        f"{generation.requested_arm.value:<9} gen {generation.ordinal}  "
        f"row {generation.hypothesis_id:>5}  "
        f"{generation.grounding.value:<12} "
        f"{len(generation.refusals)} refusal(s){mark}"
    )
for skipped in record.skipped:
    print(
        f"  bundle {skipped.bundle_id:>6}  {skipped.requested_arm.value:<9} "
        f"gen {skipped.ordinal}  SKIPPED: {redact(skipped.reason)}"
    )

report = record.budget
print("\n" + "=" * 78)
print("WHAT IT COST")
print("=" * 78)
print(f"  calls              {report.call_count} of {MAX_CALLS}")
print(f"  prompt tokens      {report.prompt_tokens}")
print(f"  completion tokens  {report.completion_tokens}")
print(f"  estimated spend    ${report.spent_usd:.4f}")
print(f"  unpriced calls     {report.unpriced_calls}")
print(f"  total is complete  {report.cost_is_complete}")

print("\n" + "=" * 78)
print("WHAT THE SAFEGUARD SAID, PER ARM")
print("=" * 78)
for arm_kind in GeneratorKind:
    rate = ledger.catch_rate(arm_kind)
    print(
        f"  {arm_kind.value:<9} checked {ledger.checked(arm_kind):>3}  "
        f"caught {ledger.caught(arm_kind):>3}  rate {rate}"
    )
print(
    "\n  The template's rate is the ORACLE: it is grounded by construction,\n"
    "  so anything flagged there is a defect in the check rather than in\n"
    "  the baseline. The hosted rate is the reported result."
)

print(f"\nwritten to {OUT.name}")
if aborted is not None:
    print(f"\n*** THE CAMPAIGN STOPPED: {aborted} ***")
    sys.stdout.flush()
    raise SystemExit(1)
sys.stdout.flush()
