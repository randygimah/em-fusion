"""Mutation pass over api-014, op-001 and nav-002: the two header labels.

Three items, one pass, because they are one change: a field leaves the payload,
the claim it half-carried splits in two, and the half that belongs everywhere
moves into the rail.

**This pass matters more than most, and the reason is in the red run.** Four of
the frontend tests passed before any implementation existed -- not because they
assert existing correct behaviour, but because a test that something is ABSENT
from the screen passes trivially while the thing it watches has not been built.
There is no coverage tooling on that side of the project at all, so this pass is
the only instrument that can say those four hold anything up.

Four surfaces.

**The standing badge reads nothing, and that is the guarantee.** It is wired to
no payload, no poll and no fetched value, so there is nothing present that can be
absent -- a dead backend, an empty store and a screen with no data all leave it
in place. The mutants attack that from both ends: derive it from the picture (the
item's named failure case), drop it when the rail collapses, and make it a nav
entry, which `nav-001` fixes at exactly three.

**A 503 is an answer and not a failure.** The sharpest mutant in the pass reads
a non-2xx from the health route as a lost connection, which reports a
misconfigured deployment as an outage -- the conflation `ops-005` exists to end,
and the state that cost a day of the main screen returning 500 while the
container called itself healthy. Its sibling collapses the two refusals into one
wording, which leaves the strip unable to say which of the two is happening.

**A renamed key must degrade visibly.** The health body is a plain dict with no
model for the contract parser to compare against, so no parity test can exist
here. The mutant removes the key check, after which a renamed field would make
the strip read `undefined`, map it to a verdict, and report a plausible steady
state forever.

**The removal is a removal.** Putting the field back, making it optional instead
of absent, and taking `rfSensors[].health` with it -- the last being the one real
risk, since the two are spelled identically and only one has a producer.

Run: `python measurements/mutation/mutate_op001_header_labels.py` from
`backend/`. `SIDE=frontend` / `SIDE=backend` runs one half; the pass of record
was taken in two parts, for the reason in README.md's third hazard.
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

SCHEMA = BACKEND / "app/api/v1/schemas/operational_picture.py"
HEALTH_ROUTE = BACKEND / "app/api/v1/health.py"
API = FRONTEND / "src/lib/api.ts"
BADGE = FRONTEND / "src/components/em/EmDataModeBadge.tsx"
STRIP = FRONTEND / "src/components/em/EmSystemStatus.tsx"
HEALTH_HOOK = FRONTEND / "src/hooks/useSystemHealth.ts"
RAIL = FRONTEND / "src/components/em/EmNavRail.tsx"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
APP = FRONTEND / "src/App.tsx"
CONTRACT = FRONTEND / "src/types/operationalPicture.ts"

FILES = (SCHEMA, HEALTH_ROUTE, API, BADGE, STRIP, HEALTH_HOOK, RAIL, SCREEN, APP, CONTRACT)

BACKEND_TESTS = [
    "tests/test_api_operational_picture.py",
    "tests/test_health.py",
    "tests/test_api_route_purity.py",
]
#: Six frontend suites. The two written for these items, plus the four that
#: already existed and that these changes reach -- the rail's collapse
#: behaviour, the navigation shell's exactly-three rule, and the two poll
#: counters that both had to be amended because a second poll now exists.
FRONTEND_TESTS = [
    "src/test/statusBar.test.tsx",
    "src/test/systemStatus.test.tsx",
    "src/test/navCollapse.test.tsx",
    "src/test/navigation.test.tsx",
    "src/test/dataAccess.test.tsx",
    "src/test/scenarioAccess.test.tsx",
]

#: name -> (file, anchor, replacement)
M: dict[str, tuple[Path, str, str]] = {
    # --- the standing badge reads nothing ------------------------------------
    "the badge is derived from the payload": (
        APP,
        "            <EmDataModeBadge collapsed={railCollapsed} />",
        "            {current.id === \"operational-picture\" && <EmDataModeBadge collapsed={railCollapsed} />}",
    ),
    "the badge is dropped when the rail collapses": (
        BADGE,
        "      {collapsed ? COLLAPSED_CLAIM : STANDING_CLAIM}",
        "      {collapsed ? \"\" : STANDING_CLAIM}",
    ),
    "the collapsed badge loses the claim and keeps the abbreviation": (
        BADGE,
        'const COLLAPSED_CLAIM = "NOT LIVE";',
        'const COLLAPSED_CLAIM = "SYN";',
    ),
    "the badge stops naming replayed data": (
        BADGE,
        'export const STANDING_CLAIM = "SYNTHETIC & REPLAYED DATA";',
        'export const STANDING_CLAIM = "SYNTHETIC ENVIRONMENT DATA";',
    ),
    "the badge loses its accessible name when collapsed": (
        BADGE,
        "    aria-label={STANDING_CLAIM}",
        "    aria-label={collapsed ? COLLAPSED_CLAIM : STANDING_CLAIM}",
    ),
    "the rail drops its footer": (
        RAIL,
        '    {footer && <div className="mt-auto flex flex-col gap-2 pt-3">{footer}</div>}',
        "    {null}",
    ),
    # --- the per-hour readout ------------------------------------------------
    "the screen prints the payload's token again": (
        SCREEN,
        "const dataModeLabel = (mode: string): string => DATA_MODE[mode] ?? \"Unrecognised data mode\";",
        "const dataModeLabel = (mode: string): string => mode;",
    ),
    "an hour with no observations reads as uncertainty": (
        SCREEN,
        '  unknown: "No observations in this hour",',
        '  unknown: "Unknown",',
    ),
    "a mixed hour names only the synthetic half": (
        SCREEN,
        '  mixed: "Synthetic RF + replayed tracks",',
        '  mixed: "Synthetic RF",',
    ),
    "the readout loses its label": (
        SCREEN,
        '            <p className="text-xs uppercase tracking-[0.05em] text-[#8c909f]">Data</p>\n',
        "",
    ),
    # --- a 503 is an answer, not a failure -----------------------------------
    "a refusal is read as a lost connection": (
        API,
        "  const response = await fetch(`${baseUrl}${SYSTEM_HEALTH_PATH}`, { signal });\n",
        "  const response = await fetch(`${baseUrl}${SYSTEM_HEALTH_PATH}`, { signal });\n"
        "  if (!response.ok) throw new Error(`${SYSTEM_HEALTH_PATH} responded ${response.status}`);\n",
    ),
    "the two refusals are given one wording": (
        STRIP,
        '  "cannot-tell": { label: "Database unreachable", tone: "bg-[#df7412]" },',
        '  "cannot-tell": { label: "Schema behind code", tone: "bg-[#df7412]" },',
    ),
    "drift is reported as healthy": (
        HEALTH_HOOK,
        '            answer.schema === "drifted"\n              ? "refusing"',
        '            answer.schema === "nonesuch"\n              ? "refusing"',
    ),
    "an unreachable database is reported as healthy": (
        HEALTH_HOOK,
        '              : answer.schema === "unknown"\n                ? "cannot-tell"',
        '              : answer.schema === "nonesuch"\n                ? "cannot-tell"',
    ),
    "a failed request is reported as connected": (
        HEALTH_HOOK,
        "        if (!cancelled) setHealth(UNREACHABLE);",
        '        if (!cancelled) setHealth({ connectivity: "up", service: "healthy" });',
    ),
    # --- a renamed key must degrade visibly ----------------------------------
    "a body missing the keys is read as a verdict": (
        API,
        '  if (typeof body?.status !== "string" || typeof body?.schema !== "string") return null;',
        "  if (false) return null;",
    ),
    "the backend stops pinning the keys the strip reads": (
        HEALTH_ROUTE,
        '            "schema": state.status,',
        '            "schemaState": state.status,',
    ),
    # --- the strip's own rules ----------------------------------------------
    "the strip reports a percentage": (
        STRIP,
        '  up: { label: "Connected", tone: "bg-[#4cd7f6]" },',
        '  up: { label: "Connected 99.9% uptime", tone: "bg-[#4cd7f6]" },',
    ),
    "a collapsed row loses its name": (
        STRIP,
        "    aria-label={`${name}: ${label}`}",
        "    aria-label={collapsed ? label : `${name}: ${label}`}",
    ),
    "the service row is dropped when the rail collapses": (
        STRIP,
        '    <Row collapsed={collapsed} name="Service" {...SERVICE[service]} />',
        '    {!collapsed && <Row collapsed={collapsed} name="Service" {...SERVICE[service]} />}',
    ),
    "the strip polls at the picture's cadence": (
        API,
        "export const SYSTEM_HEALTH_INTERVAL_MS = 15000;",
        "export const SYSTEM_HEALTH_INTERVAL_MS = 5000;",
    ),
    # --- the removal is a removal -------------------------------------------
    "the field comes back": (
        SCHEMA,
        "    id: str\n    name: str\n    dataMode: str  # noqa: N815 -- mirrors the TypeScript contract",
        "    id: str\n    name: str\n    dataMode: str  # noqa: N815 -- mirrors the TypeScript contract\n"
        '    health: str = "unknown"',
    ),
    "the field comes back as optional rather than absent": (
        SCHEMA,
        "    dataMode: str  # noqa: N815 -- mirrors the TypeScript contract\n",
        "    dataMode: str  # noqa: N815 -- mirrors the TypeScript contract\n"
        "    health: str | None = None\n",
    ),
    "the contract keeps the field the payload dropped": (
        CONTRACT,
        "export interface Scenario {\n  id: string;\n  name: string;\n  dataMode: string;\n}",
        "export interface Scenario {\n  id: string;\n  name: string;\n  dataMode: string;\n  health: string;\n}",
    ),
    "the receivers lose their own health with it": (
        SCHEMA,
        "                health=health[site.sensor_id],",
        '                health="",',
    ),
}

EXPECTED_EQUIVALENT: dict[str, str] = {}

PYTEST_RAN = re.compile(r"(\d+) (?:passed|failed)")
VITEST_RAN = re.compile(r"Tests\s+\d+")
ORIGINALS = {path: path.read_text() for path in FILES}

SIDE = os.environ.get("SIDE", "both")
if SIDE not in {"both", "backend", "frontend"}:
    raise SystemExit(f"SIDE must be backend, frontend or both, not {SIDE!r}")


#: Which suite GUARDS a file, where that is not the suite its location implies.
#: The TypeScript contract lives under `frontend/` and is held by a test in the
#: BACKEND suite: `api-002`'s parity check parses that file and compares its
#: field sets against the response models in both directions, so a field put
#: back there is caught in Python and not in vitest.
#:
#: Found by this pass rather than reasoned out in advance. Dispatching on
#: location scored the mutant that restores `scenario.health` to the contract as
#: a SURVIVOR of the frontend suite -- which it is, and which says nothing,
#: because no frontend test parses the contract and none should: the parser
#: exists once, on the side that has one. That is README.md's fifth hazard, a
#: harness scoped narrower than the thing it scores, in its most ordinary form.
GUARDED_BY: dict[Path, str] = {CONTRACT: "backend"}


def _side_of(path: Path) -> str:
    located = "frontend" if FRONTEND in path.parents else "backend"
    return GUARDED_BY.get(path, located)


if SIDE != "both":
    M = {n: m for n, m in M.items() if _side_of(m[0]) == SIDE}

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
    script = (
        'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null 2>&1; '
        "nvm use >/dev/null 2>&1; "
        f"pnpm exec vitest run {' '.join(FRONTEND_TESTS)}"
    )
    p = subprocess.run(
        ["bash", "-lc", script], cwd=str(FRONTEND), capture_output=True, text=True
    )
    both = p.stdout + p.stderr
    tail = [
        line.strip() for line in both.splitlines() if line.strip().startswith("Tests")
    ]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did vitest run?"
    return p.returncode, summary, bool(VITEST_RAN.search(summary))


def _suite_for(path: Path) -> tuple[int, str, bool]:
    return _frontend_suite() if _side_of(path) == "frontend" else _backend_suite()


for _label, _path, _from, _to, _run in (
    (
        "backend",
        HEALTH_ROUTE,
        '            "status": "healthy" if state.healthy else "unhealthy",',
        '            "status": "",',
        _backend_suite,
    ),
    (
        "frontend",
        BADGE,
        'export const STANDING_CLAIM = "SYNTHETIC & REPLAYED DATA";',
        'export const STANDING_CLAIM = "NOTHING AT ALL";',
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
