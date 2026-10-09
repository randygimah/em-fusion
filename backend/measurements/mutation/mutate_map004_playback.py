"""Mutation pass over map-004: does the map follow the playback cursor as specified?

The frontend has no coverage tooling, so this is the instrument that says
whether the map-004 tests (27 in trackPlayback.test.tsx, 6 in mapView.test.tsx)
hold anything up, with the op-008 transport tests run beside them.

**Where an aircraft is** (`lib/trackPlayback.ts`): holes interpolated across,
a held aircraft never marked, drawn before its first report, held long after
leaving, a stored gap ignored, an aircraft vanishing or unmarked while its span
loads, one known to have left held anyway, the interpolation dropped, the
reports inside a frozen gap drawn as reporting (added with the review fix).

**Trails**: too long, a broken segment where no gap was stored, the leading
broken segment dropped, the trail not reaching the aircraft.

**Zones and spans**: a zone after its window, no span loaded ahead, a span past
the hour, positions duplicated or unsorted across spans.

**The buffer** (`useTrackBuffer`): the view ignored, a span asked for twice, a
new view not starting again, loading while closed, loaded spans not recorded.

**The screen and the map**: the map handed the picture's aircraft or every zone,
no trails or trails left after closing, a stalled aircraft not named, a broken
segment undashed or in the solid colour, trails lost on a basemap switch or
never updated, a trail taking clicks; and the fetcher dropping the view.

Run: `python measurements/mutation/mutate_map004_playback.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
LIB = FRONTEND / "src/lib/trackPlayback.ts"
HOOK = FRONTEND / "src/hooks/useTrackBuffer.ts"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
MAP = FRONTEND / "src/components/map/MapView.tsx"
API = FRONTEND / "src/lib/api.ts"
FILES = (LIB, HOOK, SCREEN, MAP, API)
FRONTEND_TESTS = [
    "src/test/trackPlayback.test.tsx",
    "src/test/mapView.test.tsx",
    "src/test/playback.test.tsx",
    "src/test/transport.test.ts",
]

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- where an aircraft is
    "holes are interpolated across": (LIB, [("INTERPOLATE_WITHIN_MS = 20_000", "INTERPOLATE_WITHIN_MS = 120_000")]),
    "a departed aircraft is held ten minutes": (LIB, [("HOLD_AFTER_LAST_MS = 60_000", "HOLD_AFTER_LAST_MS = 600_000")]),
    "the interpolation is dropped": (
        LIB,
        [("track(one, here.lat + (there.lat - here.lat) * fraction, here.lon + (there.lon - here.lon) * fraction, here.altitudeFt, false)", "track(one, here.lat, here.lon, here.altitudeFt, false)")],
    ),
    "a held aircraft is never marked": (LIB, [("    tracks.push(held(since > INTERPOLATE_WITHIN_MS));", "    tracks.push(held(false));")]),
    "a stored gap is ignored after the last report": (
        LIB,
        [("    if (next < 0 && since > HOLD_AFTER_LAST_MS && !inGap(one, cursor)) continue;", "    if (next < 0 && since > HOLD_AFTER_LAST_MS) continue;")],
    ),
    "drawn before its first report": (
        LIB,
        [("    const i = lastAtOrBefore(times, cursor);\n    // Not drawn before", "    const i = Math.max(lastAtOrBefore(times, cursor), 0);\n    // Not drawn before")],
    ),
    "it vanishes while its span loads": (LIB, [("      tracks.push(held(true));\n      continue;", "      continue;")]),
    "it is unmarked while its span loads": (LIB, [("      tracks.push(held(true));\n      continue;", "      tracks.push(held(false));\n      continue;")]),
    "one known to have left is held while loading": (
        LIB,
        [("      if (loadedEdge(loaded, cursor) - times[i] > HOLD_AFTER_LAST_MS && !inGap(one, cursor)) continue;\n", "")],
    ),
    "frozen reports are drawn as reporting": (
        LIB,
        [("    const keep = times.map((time) => !gaps.some(([from, to]) => from < time && time < to));", "    const keep = times.map(() => true);")],
    ),
    # -- trails
    "the trail is five minutes": (LIB, [("TRAIL_MS = 120_000", "TRAIL_MS = 300_000")]),
    "any hole is drawn broken": (
        LIB,
        [("        if (crossesGap(times[index - 1], times[index])) segments.push", "        if (true) segments.push")],
    ),
    "the leading broken segment is dropped": (
        LIB,
        [("    if (first <= last && first > 0 && times[first] - times[first - 1]", "    if (false && first <= last && first > 0 && times[first] - times[first - 1]")],
    ),
    "the trail stops short of the aircraft": (
        LIB,
        [("    if (first <= last && next < times.length && times[last] < cursor", "    if (false && first <= last && next < times.length && times[last] < cursor")],
    ),
    # -- zones and spans
    "a zone outlives its window": (LIB, [(" && cursor <= Date.parse(zone.endedAt)", "")]),
    "no span is loaded ahead": (LIB, [("  if (index < lastIndex) spans.push(", "  if (false) spans.push(")]),
    "a span past the hour is asked for": (
        LIB,
        [("Math.min(Math.max(Math.floor((cursor - span.start) / SPAN_MS), 0), lastIndex)", "Math.max(Math.floor((cursor - span.start) / SPAN_MS), 0)")],
    ),
    "positions repeat across spans": (
        LIB,
        [("      positions: [...positions.values()].sort(", "      positions: [...known.positions, ...incoming.positions].sort(")],
    ),
    "positions are not sorted across spans": (
        LIB,
        [("      positions: [...positions.values()].sort((a, b) => Date.parse(a.time) - Date.parse(b.time)),", "      positions: [...positions.values()],")],
    ),
    # -- the buffer
    "the view is ignored": (HOOK, [("loader(runId, iso(from), iso(to), view)", 'loader(runId, iso(from), iso(to), "all")')]),
    "a span is asked for twice": (HOOK, [("      if (asked.spans.has(from)) continue;\n", "")]),
    "a new view does not start again": (
        HOOK,
        [("      requested.current = { key, spans: new Set() };", "      requested.current = { key, spans: requested.current.spans };")],
    ),
    "it loads while closed": (HOOK, [("    if (!open || !loader || key === null", "    if (!loader || key === null")]),
    "loaded spans are not recorded": (HOOK, [("loaded: [...current.loaded, [from, to]]", "loaded: current.loaded")]),
    # -- the screen
    "the map gets the picture's aircraft": (
        SCREEN,
        [("const mapTracks = playingBack ? playbackTracks(buffer.aircraft, playback.cursor, buffer.loaded) : operationalPicture.aircraftTracks;", "const mapTracks = operationalPicture.aircraftTracks;")],
    ),
    "the map gets every zone": (
        SCREEN,
        [("const mapZones = playingBack ? zonesAt(operationalPicture.interferenceZones, playback.cursor) : operationalPicture.interferenceZones;", "const mapZones = operationalPicture.interferenceZones;")],
    ),
    "the map gets no trails": (SCREEN, [("                trails={mapTrails}\n", "")]),
    "trails stay after closing": (
        SCREEN,
        [("const mapTrails = playingBack ? trailsAt(buffer.aircraft, playback.cursor) : [];", "const mapTrails = trailsAt(buffer.aircraft, playback.cursor);")],
    ),
    # -- the map
    "a stalled aircraft is not named": (MAP, [('${track.stale ? ", not reporting" : ""}', "")]),
    "a broken segment is not dashed": (
        MAP,
        [('paint: { "line-color": BROKEN_TRAIL_COLOUR, "line-width": 2, "line-dasharray": [2, 2] },', 'paint: { "line-color": BROKEN_TRAIL_COLOUR, "line-width": 2 },')],
    ),
    "a broken segment is the solid colour": (MAP, [('const BROKEN_TRAIL_COLOUR = "#ffb4ab";', 'const BROKEN_TRAIL_COLOUR = "#8c909f";')]),
    "trails are lost on a basemap switch": (MAP, [('      map.on("style.load", drawTrails);\n', "")]),
    "trails are never updated": (MAP, [("    drawTrails();\n  }, [trails, status]);", "  }, [trails, status]);")]),
    "a trail takes clicks": (
        MAP,
        [("    for (const layer of TRAIL_LAYERS) map.addLayer(layer);\n", '    for (const layer of TRAIL_LAYERS) map.addLayer(layer);\n    map.on("click", "trails-line", () => setSelected(null));\n')],
    ),
    # -- the fetcher
    "the fetcher drops the view": (API, [("new URLSearchParams({ run: String(runId), from, to, view })", "new URLSearchParams({ run: String(runId), from, to })")]),
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
MAP.write_text(ORIGINALS[MAP].replace('const TRAIL_SOURCE = "trails";', 'const TRAIL_SOURCE = "nothing";', 1))
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
