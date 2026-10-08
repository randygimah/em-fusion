"""Mutation pass over map-005 (3): does the pop-up open inside the map and move as specified?

The amendment of 8 October 2026, after review showed a pop-up near the top edge
opening with its top rows clipped. The frontend has no coverage tooling, so this
is the instrument that says whether the ten placement tests hold anything up.

**Fitting.** Always above, never below, never beside, not pulled in from the
side edges.

**Moving.** No drag, no arrow keys, the wrong step, a moved pop-up left behind
when the map pans, dragged wholly out of the map, or reopened where it was left.

**Not mutated.** The guarded pointer capture (jsdom has none, and the guard is
what lets a capture failure leave the drag working); the pop-up hidden for the one
render before its size is known (a flash, not a state any test can hold); the
18 px gap between pop-up and marker (cosmetic, no requirement names it).

Run: `python measurements/mutation/mutate_map005_popup.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
MAP = FRONTEND / "src/components/map/MapView.tsx"
FILES = (MAP,)
FRONTEND_TESTS = ["src/test/mapView.test.tsx"]

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- fitting
    "always above": (MAP, [("  if (above >= 0) return { x, y: above };", "  return { x, y: above };")]),
    "never below": (MAP, [("  if (below + popup.height <= map.height) return { x, y: below };\n", "")]),
    "never beside": (
        MAP,
        [("  const y = clamp(anchor.y - popup.height / 2, 0, map.height - popup.height);\n", "  return { x, y: clamp(above, 0, map.height - popup.height) };\n  const y = clamp(anchor.y - popup.height / 2, 0, map.height - popup.height);\n")],
    ),
    "not pulled in from the side edges": (
        MAP,
        [("  const x = clamp(anchor.x - popup.width / 2, 0, map.width - popup.width);", "  const x = anchor.x - popup.width / 2;")],
    ),
    # -- moving
    "no drag": (MAP, [("              onPointerDown={startDrag}\n", "")]),
    "no arrow keys": (MAP, [("                const delta = ARROWS[event.key];", "                const delta = undefined as Point | undefined;")]),
    "the arrow step is ten pixels": (MAP, [("const POPUP_STEP = 16;", "const POPUP_STEP = 10;")]),
    "a moved pop-up is left behind when the map pans": (
        MAP,
        [
            ("offset: { x: from.x - anchor.x + delta.x, y: from.y - anchor.y + delta.y }", "offset: { x: from.x + delta.x, y: from.y + delta.y }"),
            ("    x: clamp(anchor.x + offset.x,", "    x: clamp(offset.x,"),
            ("    y: clamp(anchor.y + offset.y,", "    y: clamp(offset.y,"),
        ],
    ),
    "a moved pop-up can leave the map": (
        MAP,
        [
            ("    x: clamp(anchor.x + offset.x, POPUP_KEEP - popup.width, map.width - POPUP_KEEP),", "    x: anchor.x + offset.x,"),
            ("    y: clamp(anchor.y + offset.y, 0, map.height - POPUP_KEEP),", "    y: anchor.y + offset.y,"),
        ],
    ),
    "a reopened pop-up keeps its move": (MAP, [("  useEffect(() => setDragged(null), [selected]);\n", "")]),
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
MAP.write_text(ORIGINALS[MAP].replace('aria-label="Map"', 'aria-label="Nothing"', 1))
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
