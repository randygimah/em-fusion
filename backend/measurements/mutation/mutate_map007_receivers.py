"""Mutation pass over map-007: are receivers drawn in their state at the cursor?

The frontend has no coverage tooling, so this is the instrument that says
whether the map-007 tests (19 in receiverPlayback.test.tsx, 1 in
mapView.test.tsx) hold anything up, with the playback suites run beside them.

**The state at the cursor** (`lib/receiverPlayback.ts`): nominal outside every
interval replaced by the whole hour's state, either bound made open, the first
interval winning rather than the worse, the ladder inverted, an unexamined hour
drawn nominal, a missing answer drawn nominal or unmarked, a receiver the
timeline does not name drawn nominal, a loaded receiver still marked.

**The hook** (`useReceiverStates`): another hour's answer accepted, asked while
closed, asked on every render, a failure never asked again, an answer for the
previous hour served for the next.

**The screen, the map and the fetcher**: the map handed the whole hour's states
during playback, or cursor states after closing, or no loader; the whole-hour
marking dropped from the name; the fetcher dropping the run, accepting a
non-answer, or returning a refusal.

Run: `python measurements/mutation/mutate_map007_receivers.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
LIB = FRONTEND / "src/lib/receiverPlayback.ts"
HOOK = FRONTEND / "src/hooks/useReceiverStates.ts"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
MAP = FRONTEND / "src/components/map/MapView.tsx"
API = FRONTEND / "src/lib/api.ts"
FILES = (LIB, HOOK, SCREEN, MAP, API)
FRONTEND_TESTS = [
    "src/test/receiverPlayback.test.tsx",
    "src/test/mapView.test.tsx",
    "src/test/playback.test.tsx",
    "src/test/trackPlayback.test.tsx",
    "src/test/transport.test.ts",
]

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- the state at the cursor
    "outside every interval reads the whole hour": (LIB, [("    let health = NOMINAL;", "    let health = sensor.health;")]),
    "the start bound is open": (LIB, [("Date.parse(interval.startedAt) <= cursor", "Date.parse(interval.startedAt) < cursor")]),
    "the end bound is open": (LIB, [("cursor <= Date.parse(interval.endedAt)", "cursor < Date.parse(interval.endedAt)")]),
    "the first interval wins, not the worse": (LIB, [("&& RANK[interval.state] > worst", "&& worst === 0")]),
    "the ladder is inverted": (LIB, [("{ fault: 2, deviating: 1 }", "{ fault: 1, deviating: 2 }")]),
    "an unexamined hour reads nominal": (LIB, [("health: NOT_EXAMINED, provisional: false", "health: NOMINAL, provisional: false")]),
    "a missing answer is unmarked": (LIB, [("if (timeline === undefined) return { ...sensor, provisional: true };", "if (timeline === undefined) return { ...sensor, provisional: false };")]),
    "a missing answer reads nominal": (LIB, [("if (timeline === undefined) return { ...sensor, provisional: true };", "if (timeline === undefined) return { ...sensor, health: NOMINAL, provisional: true };")]),
    "an unnamed receiver reads nominal": (
        LIB,
        [("states === null ? undefined : timelines.get(sensor.id);", "states === null ? undefined : (timelines.get(sensor.id) ?? { id: sensor.id, intervals: [] });")],
    ),
    "a loaded receiver is still marked": (LIB, [("return { ...sensor, health, provisional: false };", "return { ...sensor, health, provisional: true };")]),
    # -- the hook
    "another hour's answer is accepted": (HOOK, [(" && states.runId === runId", "")]),
    "asked while closed": (HOOK, [("if (!open || !loader", "if (!loader")]),
    "asked on every render": (HOOK, [(" || asked.current === runId) return;", ") return;"), ("  }, [open, runId]);", "  });")]),
    "a failure is never asked again": (HOOK, [("        if (asked.current === runId) asked.current = null;", "")]),
    "the previous hour's answer is served": (HOOK, [("return held !== null && held.runId === runId ? held : null;", "return held;")]),
    # -- the screen, the map and the fetcher
    "the map keeps whole-hour states in playback": (
        SCREEN,
        [("playingBack ? receiversAt(operationalPicture.rfSensors, receiverStates, playback.cursor) : operationalPicture.rfSensors", "operationalPicture.rfSensors")],
    ),
    "closing leaves cursor states": (
        SCREEN,
        [("playingBack ? receiversAt(operationalPicture.rfSensors, receiverStates, playback.cursor) : operationalPicture.rfSensors", "receiversAt(operationalPicture.rfSensors, receiverStates, playback.cursor)")],
    ),
    "the loader is never handed down": (SCREEN, [("useReceiverStates({ load: loadReceiverStates,", "useReceiverStates({ load: undefined,")]),
    "the whole-hour marking is not named": (MAP, [('${sensor.provisional ? ", state for the whole hour" : ""}', "")]),
    "the fetcher drops the run": (API, [("new URLSearchParams({ run: String(runId) })", "new URLSearchParams({})")]),
    "the fetcher accepts a non-answer": (API, [("if (!Array.isArray(payload?.receivers)) {", "if (false) {")]),
    "the fetcher returns a refusal": (API, [("    throw new Error(`${RECEIVER_STATES_PATH} responded ${response.status}`);\n", "")]),
}

VITEST_RAN = re.compile(r"Tests\s+\d+")
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
    script = (
        'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null 2>&1; '
        "nvm use >/dev/null 2>&1; "
        f"pnpm exec vitest run {' '.join(FRONTEND_TESTS)}"
    )
    p = subprocess.run(
        ["bash", "-lc", script], cwd=str(FRONTEND), capture_output=True, text=True
    )
    lines = [
        ln.strip()
        for ln in (p.stdout + p.stderr).splitlines()
        if ln.strip().startswith("Tests")
    ]
    summary = lines[-1] if lines else "NO TEST SUMMARY -- did vitest run?"
    return p.returncode, summary, bool(VITEST_RAN.search(summary))


# Sentinel: a deliberately broken edit must turn the suite red, or edits are not
# reaching the tests and every "killed" below would be meaningless.
LIB.write_text(ORIGINALS[LIB].replace('const NOMINAL = "nominal";', 'const NOMINAL = "nothing";', 1))
_code, _summary, _ran = _suite()
_restore()
if not _ran or not _code:
    GUARD_FILE.unlink(missing_ok=True)
    raise SystemExit(f"sentinel survived or suite did not run: {_summary}")
print(f"sentinel killed ({_summary}) -- edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for name, (path, edits) in M.items():
        mutated = ORIGINALS[path]
        bad = [old for old, _ in edits if mutated.count(old) != 1]
        if bad:
            res[name] = f"INVALID ({', '.join(str(ORIGINALS[path].count(b)) for b in bad)})"
        else:
            for old, new in edits:
                mutated = mutated.replace(old, new, 1)
            path.write_text(mutated)
            code, summary, ran = _suite()
            res[name] = (
                f"INCONCLUSIVE -- {summary}"
                if not ran
                else ("KILLED   " if code else "SURVIVED ") + summary
            )
            _restore()
        print(f"{name:52} {res[name]}", flush=True)
finally:
    _restore()
    GUARD_FILE.unlink(missing_ok=True)

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
valid = sum(1 for v in res.values() if v.startswith(("KILLED", "SURVIVED")))
print(f"\n{killed} of {valid} valid mutants killed")
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
if survived:
    print("survivors: " + ", ".join(survived))
