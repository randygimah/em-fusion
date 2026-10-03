"""Mutation pass over api-013 and op-009, asking the screen for a particular hour.

**The first pass in this repository that drives two suites.** The frontend has
no coverage tooling at all -- the 90% gate has only ever been measured on the
backend -- so `op-009` has no instrument other than this one, and a mutant in a
TypeScript file is run against vitest while a mutant in a Python file is run
against pytest in the container. Two sentinels for the same reason: each side
has to be shown to be reached before anything is read off it.

Three surfaces, and all three are about something NOT happening.

**The chooser must not carry the answer key.** The index exists only because
`/api/v1/scenario/runs` already serves a near-identical list and carries each
run's scenario type -- correctly, Scenario Control being the harness's own face,
and disqualifying on the analyst's screen. `api-012` found that string in this
screen's heading after a year. The mutants put it back, in both of the two
places it could arrive from: a field on the shape, and the frontend reaching for
the harness fetcher.

**The chooser must not carry what the detectors concluded.** Not for the
reason above -- a conclusion is what an analyst is meant to see -- but because
on this corpus precision is 1.000 and recall is 60 of 60 on every positive arm,
so a finding count would rank hours by ground truth in all but name. The mutant
adds the count.

**A pinned hour must not look like a live one, and must never be a different
hour from the one asked for.** The 404 is the sharpest case in the item:
falling back to the newest is indistinguishable from the feature working. On
the screen, the equivalent is a pinned hour rendering as though it were being
followed, or a poll that keeps asking for the newest and reverts the screen
under the analyst on the next tick.

A fourth, smaller: the replayed window must come from what the run row records
and never from its own timestamps, which are four years later than the hour
replayed (`anom-009`'s mistake).

Run: `python measurements/mutation/mutate_api013_hour_selection.py` from
`backend/`. The frontend half needs the pinned Node from `frontend/.nvmrc`,
which the runner sources the same way a developer does.

**`SIDE=backend` or `SIDE=frontend` runs one half**, and the pass of record was
taken in two parts for a reason worth keeping: the first attempt was stopped by
the OOM killer partway through, leaving a mutant in the source -- the failure
this repository had already recorded once, from the Docker builds that stopped
two earlier passes. Twenty-three mutants, most of them starting a container,
is enough churn to reach it again. Splitting the run halves the peak and lets
memory be reclaimed in between. The guard file is what makes that safe either
way: a run that dies leaves the originals recoverable, and the next run refuses
to start until they have been put back.
"""

import ast
import json
import os
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

MODELS = BACKEND / "app/dal/models.py"
REPOSITORY = BACKEND / "app/db/repository.py"
ROUTE = BACKEND / "app/api/v1/operational_picture.py"
SCHEMA = BACKEND / "app/api/v1/schemas/operational_picture.py"
API = FRONTEND / "src/lib/api.ts"
HOURS_HOOK = FRONTEND / "src/hooks/useSelectableHours.ts"
PICTURE_HOOK = FRONTEND / "src/hooks/useOperationalPicture.ts"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"

FILES = (MODELS, REPOSITORY, ROUTE, SCHEMA, API, HOURS_HOOK, PICTURE_HOOK, SCREEN)

BACKEND_TESTS = [
    "tests/test_api_hour_selection.py",
    "tests/test_api_operational_picture.py",
    "tests/test_api_route_purity.py",
]
#: Four frontend suites, not one. `dataAccess` and `operationalPicture` are
#: here because two of the mutants below are only visible as a crash or a
#: regression in them -- a guard whose only test is in the file written for the
#: item is a guard tested by the author's model of where it matters.
FRONTEND_TESTS = [
    "src/test/hourSelection.test.tsx",
    "src/test/dataAccess.test.tsx",
    "src/test/operationalPicture.test.tsx",
    "src/test/transport.test.ts",
]

#: name -> (file, anchor, replacement)
M: dict[str, tuple[Path, str, str]] = {
    # --- the answer key reaching the chooser ---------------------------------
    "the chooser carries the kind of hour": (
        MODELS,
        "    run_id: int\n"
        "    observed_from: datetime | None\n"
        "    observed_to: datetime | None\n"
        "    examined: bool",
        "    run_id: int\n"
        "    observed_from: datetime | None\n"
        "    observed_to: datetime | None\n"
        "    examined: bool\n"
        '    scenario_type: str = "gnss-degradation"',
    ),
    "the served shape carries the kind of hour": (
        SCHEMA,
        "    runId: int  # noqa: N815 -- mirrors the contract",
        "    runId: int  # noqa: N815 -- mirrors the contract\n"
        '    scenarioType: str = "gnss-degradation"  # noqa: N815',
    ),
    "the screen takes its hours from the harness's list": (
        HOURS_HOOK,
        'import { fetchSelectableHours } from "../lib/api";',
        'import { fetchScenarioRuns as fetchSelectableHours } from "../lib/api";',
    ),
    # --- what the detectors concluded ----------------------------------------
    "the chooser carries how much was found": (
        MODELS,
        "    examined: bool\n",
        "    examined: bool\n    finding_count: int = 3\n",
    ),
    # --- a different hour from the one asked for -----------------------------
    "an unknown hour is served as the newest": (
        ROUTE,
        "    if run is None and run_id is not None:",
        "    if False:",
    ),
    "the hour asked for is ignored": (
        ROUTE,
        "    run = latest_run(sessions) if run_id is None else run_summary(sessions, run_id)",
        "    run = latest_run(sessions)",
    ),
    "anything at all names an hour": (
        ROUTE,
        '    run_id: int | None = Query(default=None, alias="run"),',
        '    run_id: str | None = Query(default=None, alias="run"),',
    ),
    "the poll asks for the newest whatever is pinned": (
        PICTURE_HOOK,
        "        const picture = await fetchOperationalPicture(baseUrl, runId);",
        "        const picture = await fetchOperationalPicture(baseUrl);",
    ),
    "the selection is read once and the poll never follows it": (
        PICTURE_HOOK,
        "  }, [runId, intervalMs, baseUrl]);",
        "  }, [intervalMs, baseUrl]);",
    ),
    "the run never reaches the query string": (
        API,
        '  const query = runId === null ? "" : `?run=${encodeURIComponent(runId)}`;',
        '  const query = "";',
    ),
    # --- pinned, and looking live --------------------------------------------
    "a pinned hour says it is following the newest": (
        SCREEN,
        "              Pinned to run {pinnedRun} — not the newest.{\" \"}",
        "              Following the newest hour{\" \"}",
    ),
    "there is no way back to the newest": (
        SCREEN,
        "onClick={() => onFollowNewest?.()}",
        "onClick={() => undefined}",
    ),
    "an empty store renders a blank control": (
        SCREEN,
        '<p className="mt-1 text-xs text-[#8c909f]">No completed hour to choose from yet.</p>',
        '<p className="mt-1 text-xs text-[#8c909f]" />',
    ),
    "the control has no name a reader could ask for": (
        SCREEN,
        '              aria-label="Hour"\n',
        '              aria-label="Selection"\n',
    ),
    # --- what the chooser says about an hour ---------------------------------
    "an hour nothing examined is not offered": (
        SCREEN,
        "                  {hourLabel(hour)}",
        "                  {hourLabel(hour)}\n                  {(hour.examined ? null : (() => { throw new Error('unexamined'); })())}",
    ),
    "the label drops the replayed window": (
        SCREEN,
        "  return `Run ${hour.runId} · ${day} ${span}`;",
        "  return `Run ${hour.runId}`;",
    ),
    # --- the window, and the two clocks --------------------------------------
    "the window falls back to when the generator ran": (
        REPOSITORY,
        "                    "
        "\"  (parameters->>'start')::timestamptz AS observed_from, \"",
        "                    "
        "\"  COALESCE((parameters->>'start')::timestamptz, started_at) \"",
    ),
    "the window has no end": (
        REPOSITORY,
        '                    "    + make_interval(secs => "\n'
        '                    "        (parameters->>\'duration_seconds\')::double precision"\n'
        '                    "      ) AS observed_to, "',
        '                    "     AS observed_to, "',
    ),
    # --- which hours are offered --------------------------------------------
    "a run that did not finish is offered as an hour": (
        REPOSITORY,
        '                    "FROM scenario_runs WHERE completed_at IS NOT NULL "\n'
        '                    "ORDER BY started_at DESC, id DESC LIMIT :limit"',
        '                    "FROM scenario_runs "\n'
        '                    "ORDER BY started_at DESC, id DESC LIMIT :limit"',
    ),
    "the hours come back oldest first": (
        REPOSITORY,
        '                    "FROM scenario_runs WHERE completed_at IS NOT NULL "\n'
        '                    "ORDER BY started_at DESC, id DESC LIMIT :limit"',
        '                    "FROM scenario_runs WHERE completed_at IS NOT NULL "\n'
        '                    "ORDER BY started_at ASC, id ASC LIMIT :limit"',
    ),
    "every hour reads as examined": (
        REPOSITORY,
        '                    "  detection_pass_at IS NOT NULL AS examined "',
        '                    "  true AS examined "',
    ),
    "the bound is the harness's fifty": (
        REPOSITORY,
        "HOURS_LIMIT = 1000",
        "HOURS_LIMIT = 50",
    ),
    # --- the index's own answer ----------------------------------------------
    "an answer that is not a list is rendered anyway": (
        API,
        "  if (!Array.isArray(payload)) {",
        "  if (false) {",
    ),
}

#: "backend", "frontend", or unset for both. See the module docstring.
SIDE = os.environ.get("SIDE", "both")
if SIDE not in {"both", "backend", "frontend"}:
    raise SystemExit(f"SIDE must be backend, frontend or both, not {SIDE!r}")


def _side_of(path: Path) -> str:
    return "frontend" if FRONTEND in path.parents else "backend"


if SIDE != "both":
    M = {n: m for n, m in M.items() if _side_of(m[0]) == SIDE}

EXPECTED_EQUIVALENT: dict[str, str] = {}

PYTEST_RAN = re.compile(r"(\d+) (?:passed|failed)")
VITEST_RAN = re.compile(r"Tests\s+\d+")
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


def _backend_suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        [
            "make",
            "test-backend-nobuild",
            f"PYTEST_ARGS={' '.join(BACKEND_TESTS)} -q --no-cov",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    tail = [
        line
        for line in p.stdout.splitlines()
        if "passed" in line or "failed" in line or "error" in line
    ]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(PYTEST_RAN.search(summary))


def _frontend_suite() -> tuple[int, str, bool]:
    # The pinned Node, sourced the way a developer does: the host's default is
    # older than `.nvmrc` and pnpm refuses to start under it, which would score
    # every frontend mutant as inconclusive.
    script = (
        'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null 2>&1; '
        "nvm use >/dev/null 2>&1; "
        f"pnpm exec vitest run {' '.join(FRONTEND_TESTS)}"
    )
    p = subprocess.run(
        ["bash", "-lc", script], cwd=str(FRONTEND), capture_output=True, text=True
    )
    both = p.stdout + p.stderr
    tail = [line.strip() for line in both.splitlines() if line.strip().startswith("Tests")]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did vitest run?"
    return p.returncode, summary, bool(VITEST_RAN.search(summary))


def _suite_for(path: Path) -> tuple[int, str, bool]:
    return _frontend_suite() if _side_of(path) == "frontend" else _backend_suite()


# --- two sentinels, one per side -----------------------------------------
# Per the eighth hazard, each uses a value the code will accept, so a mutant
# killed by an import error is not mistaken for a mutant killed by a test.
for _label, _path, _from, _to, _run in (
    ("backend", REPOSITORY, "HOURS_LIMIT = 1000", "HOURS_LIMIT = 1", _backend_suite),
    (
        "frontend",
        SCREEN,
        '              aria-label="Hour"\n',
        '              aria-label="Nothing"\n',
        _frontend_suite,
    ),
):
    if SIDE not in {"both", _label}:
        continue
    assert ORIGINALS[_path].count(_from) == 1, (_label, _from)
    _path.write_text(ORIGINALS[_path].replace(_from, _to, 1))
    _code, _summary, _ran = _run()
    _restore()
    if not _ran:
        GUARD_FILE.unlink(missing_ok=True)
        raise SystemExit(f"the {_label} suite did not run at all: {_summary}")
    if not _code:
        GUARD_FILE.unlink(missing_ok=True)
        raise SystemExit(
            f"{_label.upper()} SENTINEL SURVIVED. A deliberately broken source "
            f"edit left that suite green ({_summary}), so edits are not "
            "reaching those tests."
        )
    print(f"{_label} sentinel killed ({_summary}) -- edits reach the tests", flush=True)
print(flush=True)

res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        original = ORIGINALS[path]
        if original.count(o) != 1:
            res[n] = f"INVALID ({original.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        mutated = original.replace(o, w, 1)
        if path.suffix == ".py":
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
        path.write_text(mutated)
        code, summary, ran = _suite_for(path)
        res[n] = (
            f"INCONCLUSIVE -- {summary}"
            if not ran
            else ("KILLED   " if code else "SURVIVED ") + summary
        )
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
for n, why in EXPECTED_EQUIVALENT.items():
    if n in survived:
        print(f"\nEQUIVALENT as expected: {n}\n  {why}")
