"""Mutation pass over anom-015, the detection pass.

**Almost every mutant here produces a plausible assessment.** That is the shape of
the risk and the reason the item exists: the rules each have a suite and sit at
100%, so what breaks is the *joining*, and a wrongly-joined chain does not crash.
It returns findings, claims and bundles, and reports the wrong thing about a run.
`ai-011` exists because by the time five parts worked separately, three ways of
joining them produced a system that ran perfectly and reported something false.

Five surfaces.

**The ordering.** Two rules are PostGIS queries over stored rows, so the track
findings are written before them. Reverse it and the pass finds no track evidence
and reports it *absent rather than unwritten* -- a wrong answer that looks like a
quiet corpus, on a corpus where quiet is the expected answer for two arms in five.

**The refusals.** A run still going, a run with no readings, a baseline over no
quiet runs. Each produces figures rather than an error, and the figures look
exactly like a correct result.

**Which run is read.** The pass reads its own observations precisely so the values
the rules reason from and the rows the citations resolve against are one thing.
Read a neighbouring run and findings land under the wrong id.

**The receivers behind a claim.** `anom-009` needs a count of receivers, not a
formula, because an interference zone's window is the union of its receivers'.
Hand it the wrong set and the latency is understated silently.

**The provenance.** A record carrying every required name against wrong values is
worse than an incomplete one: `eval-003` refuses the incomplete one and quotes the
wrong one as settings nothing ran under.

Needs the database, so it runs the suite through Compose.

Run: `python measurements/mutation/mutate_anom015_chain.py` from `backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MODULE = BACKEND / "app/detection/chain.py"
TESTS = ["tests/test_anom_chain.py"]

M = {
    # --- the ordering --------------------------------------------------------
    "the track findings are written after the rules that query them": (
        """    save_findings(
        session_factory,  # type: ignore[arg-type]
        scenario_run_id=run.id,
        rule_id=GAP_RULE,
        findings=gaps,
        policy=policy,
    )
""",
        "",
    ),
    "the track findings are written under the radio rule's id": (
        "        rule_id=GAP_RULE,\n        findings=gaps,",
        "        rule_id=RF_RULE,\n        findings=gaps,",
    ),
    # --- the refusals --------------------------------------------------------
    "a run still going is scored": (
        "    if run.completed_at is None:",
        "    if False:",
    ),
    "a run with no readings is scored": ("    if not rf:", "    if False:"),
    "a baseline over no quiet runs is accepted": (
        "        if not self.quiet_run_ids:",
        "        if False:",
    ),
    # --- which run is read ---------------------------------------------------
    "the radio side is read from the next run": (
        "    rf = observations_for_run(\n"
        "        session_factory,  # type: ignore[arg-type]\n"
        "        run.id,\n"
        "        ObservationType.RF,\n"
        "    )",
        "    rf = observations_for_run(\n"
        "        session_factory,  # type: ignore[arg-type]\n"
        "        run.id + 1,\n"
        "        ObservationType.RF,\n"
        "    )",
    ),
    "the aircraft side is read as radio readings": (
        "        ObservationType.TRACK,\n    )",
        "        ObservationType.RF,\n    )",
    ),
    # --- the receivers behind a claim ----------------------------------------
    "a claim's receivers come from whichever bid sorts first": (
        "            if bid.claim is claim:",
        "            if True:",
    ),
    "a claim nothing recorded receivers for gets none rather than a refusal": (
        """        raise ChainError(
            f"no receivers recorded for a {claim.rule_id} claim: this pass did not "
            "produce it, and returning none would let anom-009 measure a zone's "
            "latency from whichever receiver happened to begin first."
        )""",
        "        return ()",
    ),
    "an interference zone keeps only its first receiver": (
        "            Bid(claim=claim, sensors=tuple(zone.sensors))",
        "            Bid(claim=claim, sensors=tuple(zone.sensors)[:1])",
    ),
    # --- the account anom-008 grades against --------------------------------
    "a producer is dropped from the account": (
        "            (CLUSTER_RULE, CLUSTER_TYPE): len(self.clusters),\n",
        "",
    ),
    "the rate excess forgets the zones it declined to measure": (
        "            (GAP_RULE, EXCESS_TYPE): len(self.interference.zones)\n"
        "            + len(self.interference.declined),",
        "            (GAP_RULE, EXCESS_TYPE): len(self.interference.zones),",
    ),
    "the fault count counts every reported claim": (
        "            (FAULT_RULE, FAULT_TYPE): sum(1 for t in types if t == FAULT_TYPE),",
        "            (FAULT_RULE, FAULT_TYPE): len(types),",
    ),
    "the counts are taken over every bid rather than the reported ones": (
        "        types = [claim.anomaly_type for claim in self.reported]",
        "        types = [bid.claim.anomaly_type for bid in self.bids]",
    ),
    # --- the provenance ------------------------------------------------------
    "the baseline's quiet runs are dropped from the record": (
        '            "BASELINE.quiet_runs": ",".join(str(i) for i in normality.quiet_run_ids),\n',
        "",
    ),
    "the radio threshold is recorded from the wrong field": (
        '            "RF-NOISE.threshold_db": str(self.rf.threshold),',
        '            "RF-NOISE.threshold_db": str(self.rf.medium_at),',
    ),
    "the box is always recorded as absent": (
        '        bounds = (\n            "none"\n            if box is None',
        '        bounds = (\n            "none"\n            if True',
    ),
    "the gap threshold is recorded in minutes": (
        '            "TRACK-GAP.threshold_s": str(self.gap.threshold.total_seconds()),',
        '            "TRACK-GAP.threshold_s": str(self.gap.threshold.total_seconds() / 60),',
    ),
    # --- what it stores ------------------------------------------------------
    "the pass stores the bundles a caller did not ask it to store": (
        "    return Assessment(",
        "    from app.db.bundles import save_bundles\n\n"
        "    if bundles:\n"
        "        save_bundles(\n"
        "            session_factory,  # type: ignore[arg-type]\n"
        "            scenario_run_id=run.id,\n"
        "            bundles=bundles,\n"
        "        )\n\n"
        "    return Assessment(",
    ),
}

#: The ladder sorts bids by a declared constant, so the order they are offered in
#: cannot matter -- `anom-013`'s own point, and worth proving rather than assuming.
EXPECTED_EQUIVALENT = {
    "the bids are offered to the ladder in the other order": (
        "anom-013 sorts bids by a declared constant precisely so arrival order "
        "cannot decide a contest. A surviving mutant here is the guarantee holding."
    ),
}
M["the bids are offered to the ladder in the other order"] = (
    "    resolution = resolve([*fault_claims, *zone_claims], layout, policies.ladder)",
    "    resolution = resolve([*zone_claims, *fault_claims], layout, policies.ladder)",
)

RAN = re.compile(r"(\d+) (?:passed|failed)")
original = MODULE.read_text()

GUARD = Path(__file__).with_suffix(".in-progress.json")
if GUARD.exists():
    for name, text in json.loads(GUARD.read_text()).items():
        Path(name).write_text(text)
    GUARD.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. The "
        "original has been put back from the guard file. Check `git diff` is "
        "clean, then run again."
    )
GUARD.write_text(json.dumps({str(MODULE): original}))


def _suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        ["make", "test-backend-nobuild", f"PYTEST_ARGS={' '.join(TESTS)} -q --no-cov"],
        cwd=str(BACKEND.parent),
        capture_output=True,
        text=True,
    )
    tail = [
        line
        for line in p.stdout.splitlines()
        if "passed" in line or "failed" in line or "error" in line
    ]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(RAN.search(summary))


# --- the sentinel ---------------------------------------------------------
_from = "    if run.completed_at is None:"
assert original.count(_from) == 1
MODULE.write_text(original.replace(_from, "    if True:", 1))
_code, _summary, _ran = _suite()
MODULE.write_text(original)
if not _ran:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(f"the suite did not run at all: {_summary}")
if not _code:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(
        "SENTINEL SURVIVED. A deliberately broken source edit left the suite "
        f"green ({_summary}), so edits are not reaching the tests."
    )
print(f"sentinel killed ({_summary}) -- source edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for n, (o, w) in M.items():
        if original.count(o) != 1:
            res[n] = f"INVALID ({original.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        mutated = original.replace(o, w, 1)
        try:
            ast.parse(mutated)
        except SyntaxError as broken:
            res[n] = f"INVALID (does not parse: {broken.msg})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        if mutated == original:
            res[n] = "INVALID (identical to the original)"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        MODULE.write_text(mutated)
        code, summary, ran = _suite()
        res[n] = (
            f"INCONCLUSIVE -- {summary}"
            if not ran
            else ("KILLED   " if code else "SURVIVED ") + summary
        )
        print(f"{n:62} {res[n]}", flush=True)
        MODULE.write_text(original)
finally:
    MODULE.write_text(original)
    GUARD.unlink(missing_ok=True)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
unclear = [n for n, v in res.items() if v.startswith("INCONCLUSIVE")]
print(f"\n{killed} killed of {len(res) - len(invalid) - len(unclear)} valid mutants")
if invalid:
    print(
        f"INVALID (anchor did not match once, or the mutant does not parse): {invalid}"
    )
if unclear:
    print(f"INCONCLUSIVE (no test summary): {unclear}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
for n, why in EXPECTED_EQUIVALENT.items():
    if n in survived:
        print(f"\nEQUIVALENT as expected: {n}\n  {why}")
