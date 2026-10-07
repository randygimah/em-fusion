"""Mutation pass over anom-017: the baseline population is declared, not discovered.

Coverage says every new line ran; it cannot say a test would notice the line
being wrong. Four surfaces, and each mutant is a way the item's own failure cases
could come back without a red test.

**The pinned population.** Mutants drop a run from the constant and change a seed.
Either is a different baseline under the same name.

**The refusal.** Mutants switch off the refusal of a repeated run and of a run the
store does not hold as pinned, name only the first failing run, and stop the seed
reaching the check -- which is exactly "a pinned id that exists in the store as a
different run, accepted".

**The check itself** (`pinned_run_discrepancies`). Mutants drop each of its four
conditions in turn -- exists, quiet, finished, seed -- and report in arrival order
rather than id order.

**The callers and the measurement.** Mutants hand the batch trigger an empty or
non-pinned population, commit the measurement's transaction instead of rolling it
back, let the measurement store bundles, let the storing pass skip them, and
change how the measured sessions join the outer transaction.

Run: `python measurements/mutation/mutate_anom017_baseline.py` from `backend/`.
Needs the stack up (`make test-backend-nobuild`); about two minutes a mutant.
"""

import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
CHAIN = BACKEND / "app/detection/chain.py"
SETTINGS = BACKEND / "app/detection/settings.py"
REPOSITORY = BACKEND / "app/db/repository.py"
BATCH = BACKEND / "app/scenario/batch.py"
FILES = (CHAIN, SETTINGS, REPOSITORY, BATCH)

TESTS = [
    "tests/test_anom_baseline_pin.py",
    "tests/test_anom_measure_without_storing.py",
    "tests/test_anom_batch_trigger.py",
    "tests/test_evb_persisted.py",
]

M: dict[str, tuple[Path, str, str]] = {
    # -- the pinned population
    "a pinned run is dropped": (
        SETTINGS,
        "    PinnedRun(21, 166805981),\n",
        "",
    ),
    "a pinned seed is changed": (
        SETTINGS,
        "PinnedRun(300, 1352730131)",
        "PinnedRun(300, 1352730132)",
    ),
    # -- the refusal
    "a repeated run is not refused": (CHAIN, "    if repeated:", "    if False:"),
    "a run the store does not hold is not refused": (
        CHAIN,
        "    if discrepancies:",
        "    if False:",
    ),
    "only the first failing run is named": (
        CHAIN,
        "for run_id, why in discrepancies)",
        "for run_id, why in discrepancies[:1])",
    ),
    "the seed never reaches the check": (
        CHAIN,
        "tuple((run.run_id, run.seed) for run in quiet_runs)",
        "tuple((run.run_id, run.run_id) for run in quiet_runs)",
    ),
    # -- the check itself
    "an absent run is not reported": (
        REPOSITORY,
        '            found.append((run_id, "absent"))\n',
        "            pass\n",
    ),
    "a run that is not quiet passes": (
        REPOSITORY,
        "        if scenario_type != ScenarioType.NORMAL_BASELINE.value:",
        "        if False:",
    ),
    "an unfinished run passes": (
        REPOSITORY,
        "        elif not completed:",
        "        elif False:",
    ),
    "a run with another seed passes": (
        REPOSITORY,
        "        elif seed != wanted[run_id]:",
        "        elif False:",
    ),
    "discrepancies come back in arrival order": (
        REPOSITORY,
        "    for run_id in sorted(wanted):",
        "    for run_id in wanted:",
    ),
    # -- the callers and the measurement
    "the trigger is handed no population": (
        BATCH,
        "            quiet_runs=quiet_runs,",
        "            quiet_runs=(),",
    ),
    "the trigger's default is not the pin": (
        BATCH,
        "    quiet_runs: Sequence[PinnedRun] = BASELINE_QUIET_RUNS,",
        "    quiet_runs: Sequence[PinnedRun] = BASELINE_QUIET_RUNS[:1],",
    ),
    "the measurement is committed, not rolled back": (
        CHAIN,
        "            transaction.rollback()",
        "            transaction.commit()",
    ),
    "the measurement stores bundles": (
        CHAIN,
        "                store_bundles=False,",
        "                store_bundles=True,",
    ),
    "the storing pass skips bundles": (
        CHAIN,
        "        store_bundles=True,",
        "        store_bundles=False,",
    ),
    "the bundle write is never skipped": (
        CHAIN,
        "    if store_bundles:",
        "    if True:",
    ),
    # EQUIVALENT, recorded rather than counted as killed: SQLAlchemy's default
    # join mode never commits an external transaction either. The two differ
    # only when a session inside the pass rolls back and the pass carries on,
    # which it never does. Kept in the source because it states the intent.
    "measured sessions join without a savepoint": (
        CHAIN,
        '                join_transaction_mode="create_savepoint",\n',
        "",
    ),
}

PYTEST_RAN = re.compile(r"(\d+) (?:passed|failed)")
ORIGINALS = {path: path.read_text() for path in FILES}

GUARD_FILE = Path(__file__).with_suffix(".in-progress.json")
if GUARD_FILE.exists():
    for name, text in json.loads(GUARD_FILE.read_text()).items():
        Path(name).write_text(text)
    GUARD_FILE.unlink()
    raise SystemExit("a previous run left a mutant in the source; restored. Run again.")
GUARD_FILE.write_text(json.dumps({str(p): t for p, t in ORIGINALS.items()}))


def _restore() -> None:
    for path, text in ORIGINALS.items():
        path.write_text(text)


def _suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        ["make", "test-backend-nobuild", f"PYTEST_ARGS={' '.join(TESTS)} -q --no-cov -x"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    tail = [ln for ln in p.stdout.splitlines() if "passed" in ln or "failed" in ln or "error" in ln]
    summary = tail[-1].strip() if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(PYTEST_RAN.search(summary))


# Sentinel: a deliberately broken edit must turn the suite red, or edits are not
# reaching the container and every "killed" below would be meaningless.
CHAIN.write_text(ORIGINALS[CHAIN].replace("    if discrepancies:", "    if discrepancies or True:", 1))
_code, _summary, _ran = _suite()
_restore()
if not _ran or not _code:
    GUARD_FILE.unlink(missing_ok=True)
    raise SystemExit(f"sentinel survived or suite did not run: {_summary}")
print(f"sentinel killed ({_summary}) -- edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for name, (path, old, new) in M.items():
        original = ORIGINALS[path]
        if original.count(old) != 1:
            res[name] = f"INVALID ({original.count(old)})"
        else:
            path.write_text(original.replace(old, new, 1))
            code, summary, ran = _suite()
            res[name] = (
                f"INCONCLUSIVE -- {summary}"
                if not ran
                else ("KILLED   " if code else "SURVIVED ") + summary
            )
            _restore()
        print(f"{name:48} {res[name]}", flush=True)
finally:
    _restore()
    GUARD_FILE.unlink(missing_ok=True)

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
valid = sum(1 for v in res.values() if v.startswith(("KILLED", "SURVIVED")))
print(f"\n{killed} of {valid} valid mutants killed")
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
if survived:
    print("survivors: " + ", ".join(survived))
