"""Mutation pass over op-008: does the playback transport move the cursor as specified?

The frontend has no coverage tooling, so this is the instrument that says
whether the 24 transport tests hold anything up (22, plus two written after
the first run).

**The arithmetic** (`lib/playback.ts`): speed ignored, either end unclamped,
the frame cap removed or raised, the speeds or the step changed, the clock in
local time, the elapsed seconds unpadded, an inverted window accepted.

**The transport** (`usePlayback`): another hour not closing it, the end not
pausing, play from the end not restarting, opening away from the start or
already playing, pause resetting the cursor, a seek unclamped.

**The bar and the screen**: the time announced as a number, the play button's
name stuck, the wrong speed marked, the wrong step, the hour not pinned or
pinned again, the map handed no cursor, the button enabled with no window, the
reason dropped.

**The first run, 24 of 27.** Two survivors were killable and gained tests written
after the code: an inverted window accepted, and a seek outside the hour left
unclamped. The third is **equivalent and removed**: timing frames with
`Date.now()` instead of `performance.now()`. Under fake timers both advance one
millisecond per millisecond, so the only difference -- `Date` jumping when the
system clock is changed, where `performance.now()` is monotonic -- cannot be
expressed in a test. That the cursor never *shows or uses* today's time is
tested directly.

**The second run, 25 of 26, and the survivor is equivalent at the UI.** "A seek
is not clamped" survives the test written for it, because the slider is the
only caller and a range input sanitises its own value to `max`, in jsdom as in a
browser, so the hook never receives a moment outside the hour. The clamp is kept
for `map-004`, which may seek from elsewhere; the test pins the behaviour an
analyst sees.

**Environment-dependent mutant, recorded:** "the clock in local time" is killed
only where the test runner's zone is not UTC (it ran in Europe/London, BST).

Run: `python measurements/mutation/mutate_op008_playback.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
LIB = FRONTEND / "src/lib/playback.ts"
HOOK = FRONTEND / "src/hooks/usePlayback.ts"
BAR = FRONTEND / "src/components/em/EmPlaybackBar.tsx"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
FILES = (LIB, HOOK, BAR, SCREEN)
FRONTEND_TESTS = ["src/test/playback.test.tsx"]

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- the arithmetic
    "speed is ignored": (LIB, [("cursor + elapsedMs * speed", "cursor + elapsedMs")]),
    "the end is not clamped": (
        LIB,
        [("Math.min(Math.max(cursor + elapsedMs * speed, span.start), span.end)", "Math.max(cursor + elapsedMs * speed, span.start)")],
    ),
    "the start is not clamped": (
        LIB,
        [("Math.min(Math.max(cursor + elapsedMs * speed, span.start), span.end)", "Math.min(cursor + elapsedMs * speed, span.end)")],
    ),
    "the frame cap is removed": (LIB, [("Math.min(Math.max(now - previous, 0), MAX_FRAME_MS)", "Math.max(now - previous, 0)")]),
    "the frame cap is a second": (LIB, [("MAX_FRAME_MS = 250", "MAX_FRAME_MS = 1000")]),
    "the speeds are different": (LIB, [("[1, 4, 16, 60]", "[1, 2, 4, 8]")]),
    "a step is one second": (LIB, [("STEP_MS = 10_000", "STEP_MS = 1_000")]),
    "the clock is local time": (LIB, [("new Date(cursor).toISOString().slice(11, 19)", "new Date(cursor).toTimeString().slice(0, 8)")]),
    "elapsed seconds are unpadded": (LIB, [('String(seconds % 60).padStart(2, "0")', "String(seconds % 60)")]),
    "an inverted window is accepted": (LIB, [("end > start ? { start, end } : null", "{ start, end }")]),
    # -- the transport
    "another hour does not close it": (HOOK, [("    setOpen(false);\n    setPlaying(false);\n  }, [hour]);", "  }, [hour]);")]),
    "the end does not pause": (HOOK, [("        setPlaying(false);\n        return;\n", "")]),
    "play from the end does not restart": (HOOK, [("    if (cursorRef.current >= span.end) setCursor(span.start);\n", "")]),
    "it opens at the end": (HOOK, [("    setCursor(span.start);\n    setPlaying(false);\n    setOpen(true);", "    setCursor(span.end);\n    setPlaying(false);\n    setOpen(true);")]),
    "it opens playing": (HOOK, [("    setCursor(span.start);\n    setPlaying(false);\n    setOpen(true);", "    setCursor(span.start);\n    setPlaying(true);\n    setOpen(true);")]),
    "pause resets the cursor": (HOOK, [("    if (playing) {\n      setPlaying(false);", "    if (playing) {\n      setCursor(span.start);\n      setPlaying(false);")]),
    "a seek is not clamped": (HOOK, [("setCursor(Math.min(Math.max(to, span.start), span.end));", "setCursor(to);")]),
    # -- the bar
    "the time is announced as a number": (BAR, [("aria-valuetext={clockLabel(cursor)}", "aria-valuetext={String(cursor)}")]),
    "the play button is always Play": (BAR, [('aria-label={playing ? "Pause" : "Play"}', 'aria-label="Play"')]),
    "the first speed is always marked": (BAR, [("aria-checked={option === speed}", "aria-checked={option === 1}")]),
    "the slider steps one millisecond": (BAR, [("step={STEP_MS}", "step={1}")]),
    # -- the screen
    "the hour is not pinned": (SCREEN, [("    if (runId !== null && pinnedRun !== runId) onSelectHour?.(runId);\n", "")]),
    "the hour is pinned again": (SCREEN, [("pinnedRun !== runId) onSelectHour", "true) onSelectHour")]),
    "the map gets no cursor": (SCREEN, [("cursor={playback.open ? new Date(playback.cursor).toISOString() : null}", "cursor={null}")]),
    "the button is enabled with no window": (SCREEN, [("disabled={span === null}", "disabled={false}")]),
    "the reason is dropped": (SCREEN, [("{span === null && <span", "{false && <span")]),
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
BAR.write_text(ORIGINALS[BAR].replace('aria-label="Playback"', 'aria-label="Nothing"', 1))
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
