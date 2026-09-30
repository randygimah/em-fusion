"""What the scored campaign produced, per arm. Spec: eval-005, eval-003.

The campaign ran once, on 28 September, and cost money. `eval-005` computes
the figures it produced and has **never been run end to end**, because the
artefact the campaign wrote cannot simply be read back into the object those
figures are computed from. This closes that, and the way it closes it is the
part worth reading.

**The record does not round-trip, and says so.** `CampaignRecord.as_json`
writes the generations in full and writes the budget and the grounding
ledger as *figures* -- a total spend and a catch rate, not the calls and
checks behind them. `eval-005` needs the calls, because it reports cost and
tokens **per arm** and the stored budget is pooled across the run. So a
faithful record has to be rebuilt rather than parsed.

**Nothing here is invented; every part is recovered and then checked.**
Each call's spend and token counts come from the generation that call
produced, and each call's model id, frozen parameters and verbatim response
come from the row `db-002` stored for it -- so the reconstructed calls are
real objects carrying real values, not stand-ins shaped to fit. Two
independent totals then have to agree with what the campaign recorded at the
time, and the script **refuses to report anything** if either disagrees:

  * the rebuilt calls must sum to the stored pooled budget exactly -- same
    call count, same prompt and completion tokens, same spend, same unpriced
    count. If they do not, some call produced neither a generation nor a
    refusal, and the per-arm split would be short by that call with nothing
    saying so.
  * the rebuilt ledger must match the stored per-arm checked and caught
    counts. If it does not, the grounding figures describe a different
    population from the one being reported.

**A failed check cannot be rebuilt and is refused rather than guessed.** The
artefact records *that* a hypothesis failed grounding, never *which*
citation failed, so a ledger entry for one cannot be reconstructed
faithfully. On this campaign nothing failed, so the path is not exercised --
and it raises rather than inventing a finding, because a catch rate is a
result this project reports.

Needs the database, for the stored hypotheses. Needs no corpus and makes no
model call: it costs nothing and can be re-run freely.

Run:  make measure SCRIPT=corpus/campaign_statistics.py CORPUS=dev
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.budget import BudgetReport, CallOutcome, CallRecord
from app.ai.campaign import CampaignRecord, SkippedGeneration, generations_from_json
from app.ai.grounding import GroundingLedger, GroundingReport
from app.ai.service import GeneratorKind, ModelCall
from app.db.hypotheses import GroundingStatus, hypotheses_for_bundle
from app.evaluation.export import CampaignProvenance, export_metrics
from app.evaluation.statistics import summarise

HERE = Path(__file__).resolve().parent
EXPORTS = HERE.parent / "exports" / "campaign"

#: What the campaign ran under, from the script that ran it. Not in the
#: artefact, and `summarise` never reads it -- carried so the rebuilt report
#: is not silently a different one.
MAX_CALLS = 200
MAX_COST_USD = 3.00

record_json = json.loads((HERE / "scored_campaign_record.json").read_text())
sample_json = json.loads((HERE / "scored_sample.json").read_text())

print("the scored campaign of 28 September 2026, re-read from its own artefact")
print(f"  {len(record_json['generations'])} generations, "
      f"{len(record_json['skipped'])} skipped\n", flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

generations = generations_from_json(record_json)
skipped = tuple(
    SkippedGeneration(
        bundle_id=entry["bundle_id"],
        ordinal=entry["ordinal"],
        requested_arm=GeneratorKind(entry["requested_arm"]),
        reason=entry["reason"],
    )
    for entry in record_json["skipped"]
)

# --- the stored rows, which are where the real calls come from -------------
bundle_ids = sorted({entry["bundle_id"] for entry in sample_json["entries"]})
stored = {}
for bundle_id in bundle_ids:
    for row in hypotheses_for_bundle(factory, bundle_id):
        stored[row.id] = row
print(f"read {len(stored)} stored hypotheses across {len(bundle_ids)} bundles",
      flush=True)

wanted = {g.hypothesis_id for g in generations}
missing = sorted(wanted - set(stored))
if missing:
    raise SystemExit(
        f"{len(missing)} of {len(wanted)} generations name a hypothesis row that "
        f"is not in the database, starting at {missing[0]}. The campaign's rows "
        "have been lost or renumbered, and every figure below would describe a "
        "different population from the one that ran."
    )

# --- the budget, rebuilt from the calls that actually happened -------------
calls: list[CallRecord] = []
for generation in generations:
    row = stored[generation.hypothesis_id]
    if generation.usage is not None:
        calls.append(CallRecord(
            ordinal=len(calls) + 1,
            arm=generation.requested_arm,
            outcome=CallOutcome.SERVED,
            call=ModelCall(model_id=row.model_id or "", parameters=row.generation_params or {},
                           raw_response=row.raw_response or "", usage=generation.usage),
        ))
    for refusal in generation.refusals:
        if refusal.usage is None:
            continue
        if refusal.hypothesis_id is None or refusal.hypothesis_id not in stored:
            raise SystemExit(
                "a refused call left no stored row, so the model id, the frozen "
                "parameters and the verbatim response behind it cannot be "
                "recovered. A call rebuilt without them would be a stand-in "
                "wearing the shape of a record."
            )
        refused_row = stored[refusal.hypothesis_id]
        calls.append(CallRecord(
            ordinal=len(calls) + 1,
            arm=generation.requested_arm,
            outcome=CallOutcome.REFUSED,
            call=ModelCall(model_id=refused_row.model_id or "",
                           parameters=refused_row.generation_params or {},
                           raw_response=refused_row.raw_response or "",
                           usage=refusal.usage),
        ))

budget = BudgetReport(calls=tuple(calls), max_calls=MAX_CALLS, max_cost_usd=MAX_COST_USD)
recorded = record_json["budget"]
rebuilt = {
    "calls": budget.call_count,
    "prompt_tokens": budget.prompt_tokens,
    "completion_tokens": budget.completion_tokens,
    "spent_usd": budget.spent_usd,
    "unpriced_calls": budget.unpriced_calls,
    "cost_is_complete": budget.cost_is_complete,
}
disagree = {
    k: (rebuilt[k], recorded[k])
    for k in rebuilt
    if (abs(rebuilt[k] - recorded[k]) > 1e-9
        if isinstance(rebuilt[k], float) else rebuilt[k] != recorded[k])
}
if disagree:
    raise SystemExit(
        f"the rebuilt calls do not add up to what the campaign recorded: "
        f"{disagree}. Some call produced neither a generation nor a refusal, so "
        "the per-arm split would be short by it with nothing saying so."
    )
print(f"budget rebuilt and reconciled: {budget.call_count} calls, "
      f"${budget.spent_usd:.6f}, {budget.prompt_tokens + budget.completion_tokens} "
      "tokens -- identical to the figures recorded at the time", flush=True)

# --- the ledger, rebuilt from each generation's own verdict ----------------
ledger = GroundingLedger()
for generation in generations:
    if generation.grounding is GroundingStatus.NOT_CHECKED:
        # `ai-012`: a replacement after a fallback is not counted against the
        # arm that was asked. Not a check, so not a ledger entry.
        continue
    if generation.grounding is GroundingStatus.FAILED:
        raise SystemExit(
            f"generation {generation.ordinal} of bundle {generation.bundle_id} "
            "failed grounding, and the artefact records that it failed without "
            "recording which citation did. The ledger entry behind a catch "
            "cannot be rebuilt faithfully, and a catch rate is a result this "
            "project reports -- so this refuses rather than inventing a finding."
        )
    ledger.record(generation.requested_arm, GroundingReport(findings=()))

for arm in GeneratorKind:
    kept = record_json["grounding"][arm.value]
    if (ledger.checked(arm), ledger.caught(arm)) != (kept["checked"], kept["caught"]):
        raise SystemExit(
            f"the rebuilt ledger for {arm.value} says "
            f"{ledger.checked(arm)} checked and {ledger.caught(arm)} caught, "
            f"against {kept['checked']} and {kept['caught']} recorded at the "
            "time. The grounding figures would describe a different population."
        )
print("ledger rebuilt and reconciled against the recorded per-arm counts\n",
      flush=True)

# --- the figures -----------------------------------------------------------
record = CampaignRecord(
    generations=generations, skipped=skipped, budget=budget, ledger=ledger
)
statistics = summarise(
    record, hypotheses={row_id: row.hypothesis for row_id, row in stored.items()}
)

print("PER ARM, NEVER POOLED -- there is deliberately no campaign-wide figure")
print(f"  {'arm':10} {'gens':>5} {'bund':>5} {'checked':>8} {'caught':>7} "
      f"{'catch':>7} {'retry':>7} {'fallbk':>7} {'calls':>6} {'spend $':>9} "
      f"{'seconds':>9}")
for arm in statistics.arms:
    def show(value, places=3):
        return "--" if value is None else f"{value:.{places}f}"
    print(f"  {arm.arm.value:10} {arm.generations:5d} {arm.bundles:5d} "
          f"{arm.checked:8d} {arm.caught:7d} {show(arm.catch_rate):>7} "
          f"{show(arm.retry_rate):>7} {show(arm.fallback_rate):>7} "
          f"{arm.calls:6d} {arm.spent_usd:9.6f} {arm.seconds:9.3f}")

print("\n  the template arm is the ORACLE: it is grounded by construction, so a")
print("  non-zero catch rate there would be a defect in the check, not the arm.")

print("\nTOKENS AND COMPLETENESS")
for arm in statistics.arms:
    print(f"  {arm.arm.value:10} prompt {arm.prompt_tokens:7d}  "
          f"completion {arm.completion_tokens:6d}  unpriced {arm.unpriced_calls:3d}  "
          f"cost is {'complete' if arm.cost_is_complete else 'A LOWER BOUND'}")

print("\nAGREEMENT ACROSS REPEATED GENERATIONS -- only where an arm was asked twice")
for arm in statistics.arms:
    a = arm.agreement
    def show(value):
        return "--" if value is None else f"{value:.3f}"
    print(f"  {arm.arm.value:10} bundles {a.bundles:3d}  grounding {show(a.grounding):>6}  "
          f"confidence {show(a.confidence):>6}  cited kinds {show(a.cited_kinds):>6}")
print("  A bundle asked once reports nothing rather than a perfect score it did")
print("  not earn, which is why the template row is empty.")

# --- eval-003: the same figures as files -----------------------------------
model_ids = {row.model_id for row in stored.values() if row.model_id}
digests = {
    (row.generation_params or {}).get("prompt_sha256")
    for row in stored.values()
    if row.generation_params
}
digests.discard(None)
if len(model_ids) != 1 or len(digests) != 1:
    raise SystemExit(
        f"the stored rows name {len(model_ids)} model id(s) and {len(digests)} "
        "prompt digest(s). A campaign is one arm asked one question, and two of "
        "either means these rows are not one experiment."
    )
sample = next(
    row for row in stored.values() if row.model_id and row.generation_params
)
parameters = {
    k: v for k, v in (sample.generation_params or {}).items() if k != "prompt_sha256"
}

provenance = CampaignProvenance(
    model_id=model_ids.pop(),
    parameters=parameters,
    prompt_digest=digests.pop(),
    sample_seed=sample_json["seed"],
    population={
        kind: tuple(ids) for kind, ids in sorted(sample_json["population"].items())
    },
    measured_on="2026-09-28",
)
export = export_metrics(campaign=statistics, campaign_provenance=provenance)
EXPORTS.mkdir(parents=True, exist_ok=True)
for name, text in sorted(export.files.items()):
    (EXPORTS / name).write_text(text)
print(f"\nexported {len(export.files)} files to measurements/exports/campaign/, "
      f"every row stamped {provenance.digest}")
for name in sorted(export.files):
    print(f"  {name}")
print(f"\nre-read on {date.today().isoformat()}; the campaign itself ran "
      "2026-09-28 and is not re-run here.")
