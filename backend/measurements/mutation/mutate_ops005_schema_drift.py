"""Mutation pass over ops-005, the schema-drift guard.

**A guard is the worst kind of code to get wrong, because wrong means silent.**
Every mutant here leaves a service that starts, answers, and reports itself
healthy -- which is precisely the state the item exists to end. The defect of
record lasted a day in exactly that condition: the main screen returned 500, the
health route answered 200, and `docker compose ps` said healthy throughout.

Four surfaces.

**Where the expectation comes from.** Read out of the version table -- the table
being checked -- the comparison agrees with itself on every database there is. It
passes everywhere and has no failure case, and it looks exactly like a working
guard. The mutant that does this is the one worth having.

**The three states, and that the third is not a refusal.** An unreachable
database must answer 200 and say it could not tell, because an outage is not a
misconfiguration and refusing on one does what `api-001` was written to avoid.
The mutants collapse the three into two in both directions: refusing on an
outage, and passing on drift.

**Each half cached for exactly as long as it stays true.** The expectation is
cached for the life of the process because it cannot change without restarting
it; the database's revision is read on every probe because a migration applied to
a live stack has to clear the refusal on the next one. Swap either and the guard
is wrong in a way nothing notices until somebody is already debugging.

**The status code, and the Makefile.** 503 rather than a 200 carrying a sad
field, because the probe only reports unhealthy on a non-2xx -- a body nobody
parses is what we already had. And both start commands migrate first, because a
guard that fires on every first run is one somebody switches off.

Runs in the container: three of the tests are database-tier, including the one
that moves a real database back a revision, and a host-only run would score their
mutants as survivors of a suite that never ran them.

Run: `python measurements/mutation/mutate_ops005_schema_drift.py` from `backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MIGRATIONS = BACKEND / "app/db/migrations.py"
REPOSITORY = BACKEND / "app/db/repository.py"
HEALTH = BACKEND / "app/api/v1/health.py"
MAKEFILE = BACKEND.parent / "Makefile"
FILES = (MIGRATIONS, REPOSITORY, HEALTH, MAKEFILE)
TESTS = [
    "tests/test_ops_schema_drift.py",
    "tests/test_health.py",
    "tests/test_api_route_purity.py",
]

#: name -> (file, anchor, replacement)
M: dict[str, tuple[Path, str, str]] = {
    # --- where the expectation comes from ------------------------------------
    "the expectation is read from the database it is checking": (
        REPOSITORY,
        "    return compare_schema(heads_on_disk(alembic_config()), found)",
        "    return compare_schema((found,) if found else (), found)",
    ),
    "any head will do when the graph has several": (
        MIGRATIONS,
        "    return heads[0] if len(heads) == 1 else None",
        "    return heads[0] if heads else None",
    ),
    "a graph with two heads is compared against one of them": (
        MIGRATIONS,
        "    if len(heads) != 1:",
        "    if not heads:",
    ),
    # --- the three states ----------------------------------------------------
    "a database nobody has migrated reads as up to date": (
        MIGRATIONS,
        "    if found is None:",
        "    if False:",
    ),
    "an unreachable database is reported as drifted": (
        MIGRATIONS,
        '        status=UNKNOWN,\n        expected=expected_revision(),\n        found=None,',
        '        status=DRIFTED,\n        expected=expected_revision(),\n        found=None,',
    ),
    "a process with no engine is an error rather than an unknown": (
        REPOSITORY,
        '    if session_factory is None:\n'
        '        return unreachable("no engine has been built in this process")',
        "    if session_factory is None:\n"
        '        raise RuntimeError("no engine")',
    ),
    "a database that cannot be read is reported as up to date": (
        REPOSITORY,
        "    except Exception as unreadable:  # noqa: BLE001 -- reported, never raised\n"
        '        return unreachable(f"{type(unreadable).__name__}")',
        "    except Exception:  # noqa: BLE001\n"
        "        return compare_schema(heads_on_disk(alembic_config()), None)",
    ),
    "an absent version table is told apart from an outage by exception class": (
        REPOSITORY,
        '            versioned = session.execute(\n'
        "                text(\"SELECT to_regclass('alembic_version') IS NOT NULL\")\n"
        "            ).scalar_one()",
        "            versioned = True",
    ),
    "a version table holding no row reads as up to date": (
        REPOSITORY,
        "                ).scalar_one_or_none()",
        '                ).scalar_one_or_none() or "0009_detection_pass_stamp"',
    ),
    # --- what healthy means --------------------------------------------------
    "drift is healthy after all": (
        MIGRATIONS,
        "        return self.status != DRIFTED",
        "        return True",
    ),
    "not knowing is treated as unhealthy": (
        MIGRATIONS,
        "        return self.status != DRIFTED",
        "        return self.status == AT_HEAD",
    ),
    "the refusal is a 200 carrying a sad field": (
        HEALTH,
        "        status_code=200 if state.healthy else 503,",
        "        status_code=200,",
    ),
    "the body stops naming what it found": (
        HEALTH,
        '            "found": state.found,',
        '            "found": None,',
    ),
    "the body stops naming what was expected": (
        HEALTH,
        '            "expected": state.expected,',
        '            "expected": None,',
    ),
    "the detail no longer names the revision in force": (
        MIGRATIONS,
        '            f"this database is at {found} and this code expects {expected}. If it is "',
        '            "this database is not at the expected revision. "',
    ),
    "a database ahead of the code is not called out as ahead": (
        MIGRATIONS,
        'f"behind, run `make migrate`; if it is ahead, this code is older than the "',
        '"behind, run `make migrate`. "',
    ),
    # --- what is cached, and for how long ------------------------------------
    "the database's revision is cached and the refusal outlives it": (
        REPOSITORY,
        "def schema_state(session_factory: sessionmaker[Session] | None) -> SchemaState:",
        "@__import__(\"functools\").lru_cache(maxsize=1)\n"
        "def schema_state(session_factory: sessionmaker[Session] | None) -> SchemaState:",
    ),
    # --- the first run -------------------------------------------------------
    "starting the stack no longer applies the migrations": (
        MAKEFILE,
        "up: migrate ## Apply migrations, then start backend + frontend in the background",
        "up: ## Start backend + frontend in the background",
    ),
    "the demo target no longer applies the migrations": (
        MAKEFILE,
        "demo: ensure-artifacts migrate ## Apply migrations, then run the full stack in the foreground",
        "demo: ensure-artifacts ## Build and run the full stack in the foreground",
    ),
}

EXPECTED_EQUIVALENT: dict[str, str] = {}

RAN = re.compile(r"(\d+) (?:passed|failed)")
ORIGINALS = {path: path.read_text() for path in FILES}

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
# A value the objects will accept, per the eighth hazard: a mutant that cannot be
# imported is killed by an error rather than by a test and says nothing.
_from = "        return self.status != DRIFTED"
assert ORIGINALS[MIGRATIONS].count(_from) == 1
MIGRATIONS.write_text(ORIGINALS[MIGRATIONS].replace(_from, "        return True", 1))
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
            print(f"{n:70} {res[n]}", flush=True)
            continue
        mutated = original.replace(o, w, 1)
        if path.suffix == ".py":
            try:
                ast.parse(mutated)
            except SyntaxError as broken:
                res[n] = f"INVALID (does not parse: {broken.msg})"
                print(f"{n:70} {res[n]}", flush=True)
                continue
        if mutated == original:
            res[n] = "INVALID (identical to the original)"
            print(f"{n:70} {res[n]}", flush=True)
            continue
        path.write_text(mutated)
        code, summary, ran = _suite()
        res[n] = (
            f"INCONCLUSIVE -- {summary}"
            if not ran
            else ("KILLED   " if code else "SURVIVED ") + summary
        )
        print(f"{n:70} {res[n]}", flush=True)
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
for n, why in EXPECTED_EQUIVALENT.items():
    if n in survived:
        print(f"\nEQUIVALENT as expected: {n}\n  {why}")
