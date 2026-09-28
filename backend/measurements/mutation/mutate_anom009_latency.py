"""Mutation pass over anom-009, detection latency.

**Every mutant here returns a number of seconds.** Nothing raises, nothing
looks wrong, and the damage is a latency figure that is plausible and false
-- which is the worst possible shape for a measurement that will be quoted
in a results table and never sanity-checked against anything.

Four surfaces, and one of them is the item.

**The receiver requirement.** `anom-005`'s zone window is the *union* of its
receivers' windows, so measuring it as though one receiver sufficed reports
the moment the *first* receiver's evidence matured, understating the latency
by however long the receivers were staggered. That mutant is the design
decision made visible: if the suite does not kill it, the whole table is
wrong in the direction that flatters the system.

**The minimum.** Dropping it reports the moment evidence *started* rather
than the moment it was *sufficient*, which is the "first cited reading"
definition this item explicitly rejected -- and it would report near-zero
latency everywhere, truly and vacuously. Taking the episode's end instead of
its start reports when the event finished.

**The sign.** Clamping a negative latency to zero turns "the rule swept in
readings from before the incident" into "the rule detected it instantly",
which is the exact inversion the no-clamping rule exists to prevent.

**The refusals.** A rule with no declared requirement defaulting to one, and
a claim with too little evidence being measured anyway.

Unlike most harnesses here this one needs no database and no corpus, because
the module it scores reads neither -- so it runs the suite directly rather
than through Compose, and a pass takes seconds rather than minutes.

Run: `python measurements/mutation/mutate_anom009_latency.py` from `backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MODULE = BACKEND / "app/detection/latency.py"
TESTS = ["tests/test_anom_latency.py"]

M = {
    # --- the receiver requirement: the item itself ---------------------------
    "interference is measured as though one receiver sufficed": (
        "    FUSION_RULE_ID: 2,",
        "    FUSION_RULE_ID: 1,"),
    "a broken receiver is measured as though two were needed": (
        "    FAULT_RULE_ID: 1,",
        "    FAULT_RULE_ID: 2,"),
    "the nth qualification becomes the first": (
        "    decidable_at = order[required - 1][1]",
        "    decidable_at = order[0][1]"),
    "the nth qualification becomes the last": (
        "    decidable_at = order[required - 1][1]",
        "    decidable_at = order[-1][1]"),

    # --- the minimum: what "sufficient" means -------------------------------
    "the minimum is dropped, so evidence starting counts as evidence enough": (
        "        at = episode.started_at + minimum",
        "        at = episode.started_at"),
    "the episode's end is taken instead of its start": (
        "        at = episode.started_at + minimum",
        "        at = episode.ended_at + minimum"),
    "the minimum is counted twice": (
        "        at = episode.started_at + minimum",
        "        at = episode.started_at + minimum + minimum"),
    "a receiver qualifies on its latest episode rather than its earliest": (
        "        if sensor not in qualified or at < qualified[sensor]:",
        "        if sensor not in qualified or at > qualified[sensor]:"),

    # --- the sign ------------------------------------------------------------
    "a negative latency is clamped to zero": (
        "        latency=decidable_at - onset,",
        "        latency=max(decidable_at - onset, timedelta(0)),"),
    "the subtraction runs the other way": (
        "        latency=decidable_at - onset,",
        "        latency=onset - decidable_at,"),

    # --- what counts as this claim's evidence -------------------------------
    "every receiver's episodes count, not only this claim's": (
        "        if sensor not in wanted:\n            continue",
        "        if False:\n            continue"),

    # --- the refusals --------------------------------------------------------
    "an undeclared rule defaults to one receiver": (
        "    required = RECEIVERS_REQUIRED.get(claim.rule_id)\n"
        "    if required is None:",
        "    required = RECEIVERS_REQUIRED.get(claim.rule_id, 1)\n"
        "    if False:"),
    "too little evidence is measured anyway": (
        "    if len(qualified) < required:",
        "    if False:"),
    "a negative minimum is accepted": (
        "    if minimum < timedelta(0):",
        "    if False:"),

    # --- how it is reported --------------------------------------------------
    "the resolution is dropped from the report": (
        '            "minimum_seconds": self.minimum.total_seconds(),\n',
        ""),
}

#: None. Every mutant above changes a number the write-up would quote.
EXPECTED_EQUIVALENT: set[str] = set()

RAN = re.compile(r"(\d+) (?:passed|failed)")
original = MODULE.read_text()

GUARD = Path(__file__).with_suffix(".in-progress.json")
if GUARD.exists():
    for name, text in json.loads(GUARD.read_text()).items():
        Path(name).write_text(text)
    GUARD.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. "
        "The original has been put back from the guard file. Check `git diff` "
        "is clean, then run again."
    )
GUARD.write_text(json.dumps({str(MODULE): original}))


def _suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        [".venv/bin/python", "-m", "pytest", *TESTS,
         "-q", "--no-header", "-p", "no:cacheprovider", "--no-cov"],
        cwd=str(BACKEND), capture_output=True, text=True)
    tail = [line for line in p.stdout.splitlines()
            if "passed" in line or "failed" in line or "error" in line]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(RAN.search(summary))


# --- the sentinel ---------------------------------------------------------
# A deliberately broken edit. If the suite stays green, edits are not
# reaching the tests and no score from this harness means anything.
_from = "    if minimum < timedelta(0):"
assert original.count(_from) == 1
MODULE.write_text(original.replace(_from, "    if False:", 1))
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
        # **A mutant that does not parse tests nothing.** Recorded twice in
        # this repository and commented on in `mutate_ai012_campaign.py`
        # without ever being enforced there: a mutant producing an
        # IndentationError is killed by a syntax error rather than by a
        # test, which scores a gap as a pass. Checked here rather than
        # inferred from a missing summary.
        try:
            ast.parse(mutated)
        except SyntaxError as broken:
            res[n] = f"INVALID (does not parse: {broken.msg})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        MODULE.write_text(mutated)
        code, summary, ran = _suite()
        res[n] = (f"INCONCLUSIVE -- {summary}" if not ran
                  else ("KILLED   " if code else "SURVIVED ") + summary)
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
    print(f"INVALID (anchor did not match once, or the mutant does not parse): {invalid}")
if unclear:
    print(f"INCONCLUSIVE (no test summary): {unclear}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
