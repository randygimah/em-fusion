"""Mutation pass over api-011, one batch at a time.

**Almost every mutant here leaves the endpoint working.** That is the shape of
the risk. A start still answers 202, a batch still runs, the runs still appear
in the table -- and the bound is simply not there, which is invisible until
somebody presses the button twice on a loaded machine and the backend stops
serving. The defect this item fixes was found that way and not by a test.

Four surfaces, and the first two are the item itself.

**The bound.** Disable the refusal, or claim the guard without storing it, and
the endpoint behaves exactly as it did before this item existed.

**Who releases, and when.** Two mutants at opposite ends of one decision.
Released where the launcher returns, the guard is free before a single run row
is opened -- not a weaker bound but no bound at all. Released outside a
`finally`, one failing batch holds it until the container restarts, which turns
a recoverable error into an outage of the same kind the guard exists to
prevent. Both need a thread stand-in that does *not* run its target, because
under an inline one the batch always finishes and both arrangements look
identical.

**What the refusal says.** An analyst who cannot tell which batch is in flight
cannot tell whether to wait or to investigate. Name the batch that was just
refused instead of the one that is running and the answer is worthless while
looking complete -- and it reads as correct on any test posting one
configuration twice.

**The clock.** `anom-009` exists because a wall-clock timestamp once wore a
simulated-time costume. Here the wall clock is right, and a naive one is the
mutant: it still renders, still sorts, and is an hour out wherever the host is
not on UTC.

Three files, because the item is a seam: the guard decides, the route consults,
the thread releases. Needs no database and no corpus.

Run: `python measurements/mutation/mutate_api011_guard.py` from `backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
GUARD_MODULE = BACKEND / "app/scenario/guard.py"
ROUTE_MODULE = BACKEND / "app/api/v1/scenario.py"
BATCH_MODULE = BACKEND / "app/scenario/batch.py"
TESTS = ["tests/test_api_scenario.py", "tests/test_scn_control_contract.py"]

#: name -> (file, anchor, replacement)
M: dict[str, tuple[Path, str, str]] = {
    # --- the bound -----------------------------------------------------------
    "a second batch is admitted, as before this item existed": (
        GUARD_MODULE,
        "            if self._held is not None:",
        "            if False:"),
    "the guard is claimed and never stored, so every start is the first": (
        GUARD_MODULE,
        "            self._held = Lease(self, in_flight)\n            return self._held",
        "            return Lease(self, in_flight)"),
    "the guard is taken and read without the lock held across both": (
        GUARD_MODULE,
        "        with self._lock:\n"
        "            if self._held is not None:\n"
        "                raise BatchAlreadyRunning(self._held.in_flight)\n"
        "            self._held = Lease(self, in_flight)\n"
        "            return self._held",
        "        held = self.in_flight\n"
        "        if held is not None:\n"
        "            raise BatchAlreadyRunning(held)\n"
        "        with self._lock:\n"
        "            self._held = Lease(self, in_flight)\n"
        "            return self._held"),
    "nothing is ever reported as in flight": (
        GUARD_MODULE,
        "            return None if self._held is None else self._held.in_flight",
        "            return None"),

    # --- who releases, and when ----------------------------------------------
    "a release frees whichever batch is holding, not the lease's own": (
        GUARD_MODULE,
        "            if self._held is lease:",
        "            if True:"),
    "release does nothing at all": (
        GUARD_MODULE,
        "            if self._held is lease:\n                self._held = None",
        "            if self._held is lease:\n                pass"),
    "the lease is released where the launcher returns": (
        BATCH_MODULE,
        "        finally:\n"
        "            lease.release()\n"
        "\n"
        '    Thread(target=work, name="scenario-batch", daemon=True).start()',
        "\n"
        '    Thread(target=work, name="scenario-batch", daemon=True).start()\n'
        "    lease.release()"),
    "a batch that fails never gives the guard back": (
        BATCH_MODULE,
        "        finally:\n            lease.release()",
        "        else:\n            lease.release()"),
    "a launcher that cannot start its thread leaves the guard held": (
        ROUTE_MODULE,
        "    except Exception:\n        lease.release()\n        raise",
        "    except Exception:\n        raise"),

    # --- what the refusal says -----------------------------------------------
    "the refusal names the batch it just refused, not the running one": (
        GUARD_MODULE,
        "                raise BatchAlreadyRunning(self._held.in_flight)",
        "                raise BatchAlreadyRunning(in_flight)"),
    "the refusal is prose rather than fields": (
        ROUTE_MODULE,
        "            detail=BatchInFlight(\n"
        "                scenarioType=running.scenario_type.value,\n"
        "                baseSeed=running.base_seed,\n"
        "                startedAt=running.started_at,\n"
        '            ).model_dump(mode="json"),',
        "            detail=str(refusal),"),
    "the refusal loses the seed that identifies the batch": (
        ROUTE_MODULE,
        "                baseSeed=running.base_seed,",
        "                baseSeed=0,"),
    "a second start is refused with the status of a bad request": (
        ROUTE_MODULE,
        "            status_code=409,",
        "            status_code=422,"),
    "the refusal carries the run's own parameters as well": (
        ROUTE_MODULE,
        "            detail=BatchInFlight(",
        "            detail={**batch.incident.model_dump(mode=\"json\")}\n"
        "            | BatchInFlight("),

    # --- the clock -----------------------------------------------------------
    "the start time is recorded without a timezone": (
        ROUTE_MODULE,
        "                started_at=datetime.now(UTC),",
        "                started_at=datetime.now(),"),

    # --- the process the state belongs to ------------------------------------
    "each request is given a guard of its own": (
        ROUTE_MODULE,
        "    return BATCH_GUARD",
        "    return BatchGuard()"),
    "the shipped launcher runs nothing": (
        ROUTE_MODULE,
        "    return launch_batch",
        "    return lambda request, lease: None"),
}

EXPECTED_EQUIVALENT: dict[str, str] = {}

RAN = re.compile(r"(\d+) (?:passed|failed)")
ORIGINALS = {path: path.read_text() for path in (GUARD_MODULE, ROUTE_MODULE, BATCH_MODULE)}

GUARD_FILE = Path(__file__).with_suffix(".in-progress.json")
if GUARD_FILE.exists():
    for name, text in json.loads(GUARD_FILE.read_text()).items():
        Path(name).write_text(text)
    GUARD_FILE.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. "
        "The originals have been put back from the guard file. Check `git diff` "
        "is clean, then run again."
    )
GUARD_FILE.write_text(json.dumps({str(p): t for p, t in ORIGINALS.items()}))


def _restore() -> None:
    for path, text in ORIGINALS.items():
        path.write_text(text)


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
# A deliberately broken edit. If the suite stays green, edits are not reaching
# the tests and no score from this harness means anything.
_from = "        with self._lock:\n            if self._held is not None:"
assert ORIGINALS[GUARD_MODULE].count(_from) == 1
GUARD_MODULE.write_text(
    ORIGINALS[GUARD_MODULE].replace(_from, "        with self._lock:\n            if True:", 1)
)
_code, _summary, _ran = _suite()
_restore()
if not _ran:
    GUARD_FILE.unlink(missing_ok=True)
    raise SystemExit(f"the suite did not run at all: {_summary}")
if not _code:
    GUARD_FILE.unlink(missing_ok=True)
    raise SystemExit(
        "SENTINEL SURVIVED. A deliberately broken source edit left the suite "
        f"green ({_summary}), so edits are not reaching the tests."
    )
print(f"sentinel killed ({_summary}) -- source edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        original = ORIGINALS[path]
        if original.count(o) != 1:
            res[n] = f"INVALID ({original.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        mutated = original.replace(o, w, 1)
        # A mutant that does not parse tests nothing: it is killed by a syntax
        # error rather than by a test, which scores a gap as a pass.
        try:
            ast.parse(mutated)
        except SyntaxError as broken:
            res[n] = f"INVALID (does not parse: {broken.msg})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        # A mutant identical to the original tests nothing either, and reads as
        # a survivor -- the sixth hazard in measurements/README.md.
        if mutated == original:
            res[n] = "INVALID (identical to the original)"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        path.write_text(mutated)
        code, summary, ran = _suite()
        res[n] = (f"INCONCLUSIVE -- {summary}" if not ran
                  else ("KILLED   " if code else "SURVIVED ") + summary)
        print(f"{n:62} {res[n]}", flush=True)
        _restore()
finally:
    _restore()
    GUARD_FILE.unlink(missing_ok=True)
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
