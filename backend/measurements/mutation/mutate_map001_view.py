"""Mutation pass over map-001, map-002, map-003 and map-005: does the map hold its promises?

The frontend has no coverage tooling, so this is the instrument that says
whether the map tests (48 on the adapter, 6 on the boundary) and the
re-pointed exception-panel test hold anything up. MapLibre needs WebGL, which
jsdom lacks, so every mutant here lands in what surrounds the drawing.

**Configuration and the default style.** Off-origin archives, satellite with one
variable, CDN glyphs or sprite, missing credits, a relative sprite, the dark
flavour or sprite back, the box drawing from zoom 0 or with its own background,
overview labels at every zoom, the camera leaving Europe, the overview unread.

**The three non-map states.** The library loaded unconfigured, the archive
unread, a missing archive worded as unconfigured, a failed start shown as a
map, the counts dropped.

**Markers and states.** Latitude first, markers that never move or outlive
their rows, unknown named as the word, deviating not anomalous, unexamined or
anomalous drawn as nominal, one nominal colour for both kinds.

**The pop-up and labels.** An invented speed, a dropped band, a marker that
opens nothing, Escape or a map click that closes nothing, a pop-up kept for a
vanished entity; aircraft labelled at every zoom or never, labels placed in
arrival order or allowed to overlap, any icon hiding any label, an anomalous
receiver ranked like the rest.

**The map and the screen.** Satellite offered unconfigured, started on, fallen
back from silently or failing unstated; the worker URL; the map's aircraft and
the placeholder.

Run: `python measurements/mutation/mutate_map001_view.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
MAP = FRONTEND / "src/components/map/MapView.tsx"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
FILES = (MAP, SCREEN)
FRONTEND_TESTS = [
    "src/test/mapView.test.tsx",
    "src/test/mapBoundary.test.tsx",
    "src/test/exceptionPanel.test.tsx",
    "src/test/operationalPicture.test.tsx",
]

DEFAULT_START = "style: onThisOrigin(buildDefaultStyle(archive)),"
# Not mutated: a new marker placed latitude first. The marker pass runs on every
# render and re-places existing markers, so a swapped first placement is
# corrected on the render its own setHosts triggers -- equivalent in behaviour,
# found as a survivor on the first run and removed rather than tested around.
# The steady-state order is mutated by "markers never move" and asserted by the
# marker tests.

M: dict[str, tuple[Path, str, str]] = {
    # -- configuration
    "any archive address is accepted": (
        MAP,
        r"!/^\/[^/]/.test(defaultArchive)",
        "false",
    ),
    "a protocol-relative archive is accepted": (
        MAP,
        r"!/^\/[^/]/.test(",
        r"!/^\//.test(",
    ),
    "satellite is offered with one variable set": (
        MAP,
        "tiles && attribution ?",
        "tiles || attribution ?",
    ),
    # -- the default style
    "glyphs come from the CDN": (
        MAP,
        "glyphs: `${folder}/fonts/",
        "glyphs: `https://protomaps.github.io/basemaps-assets/fonts/",
    ),
    "the sprite comes from the CDN": (
        MAP,
        "sprite: `${folder}/sprites/v4/light`",
        "sprite: `https://protomaps.github.io/basemaps-assets/sprites/v4/light`",
    ),
    "OpenStreetMap is not credited": (
        MAP,
        'DEFAULT_ATTRIBUTION = "© OpenStreetMap contributors · Protomaps"',
        'DEFAULT_ATTRIBUTION = "Protomaps"',
    ),
    "satellite is not credited": (
        MAP,
        "attribution: satellite.attribution",
        'attribution: ""',
    ),
    "the configured archive is ignored": (
        MAP,
        "url: `pmtiles://${archive}`",
        'url: "pmtiles:///basemap/other.pmtiles"',
    ),
    "the sprite reaches MapLibre relative": (
        MAP,
        DEFAULT_START,
        "style: buildDefaultStyle(archive),",
    ),
    "the dark flavour comes back": (MAP, 'namedFlavor("light")', 'namedFlavor("dark")'),
    "the dark sprite comes back": (MAP, "sprites/v4/light`", "sprites/v4/dark`"),
    "the box draws from zoom 0": (MAP, "minzoom: DETAIL_FROM_ZOOM }", "minzoom: 0 }"),
    "the box keeps its own background": (
        MAP,
        '.filter((layer) => layer.type !== "background")',
        ".filter(() => true)",
    ),
    "overview labels draw at every zoom": (
        MAP,
        "maxzoom: Math.min(layer.maxzoom ?? 24, DETAIL_FROM_ZOOM)",
        "maxzoom: layer.maxzoom ?? 24",
    ),
    "the camera leaves Europe": (MAP, "          maxBounds: OVERVIEW_BOUNDS,\n", ""),
    "the overview is never read": (
        MAP,
        "Promise.all([readArchive(archive), readArchive(overviewArchive(archive))])",
        "Promise.all([readArchive(archive)])",
    ),
    # -- the three non-map states
    "the library loads with nothing configured": (
        MAP,
        "    if (!archive) return;\n",
        '    if (!archive) {\n      void import("maplibre-gl");\n      return;\n    }\n',
    ),
    "the archive is never read": (
        MAP,
        "await Promise.all([readArchive(archive), readArchive(overviewArchive(archive))]);",
        "",
    ),
    "a missing archive reads as unconfigured": (
        MAP,
        "could not be read. Download",
        "is not configured. Download",
    ),
    "a failed start is treated as a map": (
        MAP,
        'setStatus("failed");',
        'setStatus("map");',
    ),
    "the entity counts are dropped": (
        MAP,
        '<p className="font-mono text-xs text-[#8c909f]">{counts}</p>',
        "",
    ),
    # -- markers (map-001 (12))
    "markers never move": (
        MAP,
        "existing.marker.setLngLat([entity.lon, entity.lat]);",
        "",
    ),
    "markers outlive their rows": (
        MAP,
        "      marker.remove();\n      current.delete(key);",
        "      current.delete(key);",
    ),
    # -- states (map-003)
    "unknown is named as the word": (
        MAP,
        'state === "unknown" ? "not examined" : state',
        "state",
    ),
    "deviating is not anomalous": (
        MAP,
        'new Set(["fault", "deviating", "interrupted"])',
        'new Set(["fault", "interrupted"])',
    ),
    "unexamined looks nominal": (
        MAP,
        'if (state === "nominal") return',
        "if (true) return",
    ),
    "both kinds share a nominal colour": (
        MAP,
        'kind === "aircraft" ? "#005ac2" : "#00424e"',
        '"#005ac2"',
    ),
    "anomalous looks nominal": (
        MAP,
        'if (ANOMALOUS.has(state)) return { fill: "#df7412", stroke: "#ffffff" };\n',
        "",
    ),
    # -- the pop-up (map-005 (1))
    "the pop-up invents a speed": (
        MAP,
        '["Altitude", altitude(track.altitudeFt)],',
        '["Altitude", altitude(track.altitudeFt)],\n          ["Speed", "410 kts"],',
    ),
    "the pop-up drops the band": (MAP, '          ["Band", sensor.signalId],\n', ""),
    "a marker click never opens a pop-up": (
        MAP,
        "setSelected(entity.key);",
        "setSelected(null);",
    ),
    "Escape does not close": (
        MAP,
        'if (event.key === "Escape") setSelected(null);',
        "",
    ),
    "a map click does not close": (
        MAP,
        "        setSelected(null);\n      });",
        "      });",
    ),
    "a vanished entity keeps its pop-up": (
        MAP,
        "if (selected && !popup) setSelected(null);",
        "",
    ),
    # -- labels (map-005 (2))
    "every aircraft is labelled at any zoom": (
        MAP,
        "zoom < ALL_AIRCRAFT_LABELS_FROM_ZOOM",
        "false",
    ),
    "no aircraft is labelled from zoom 9": (
        MAP,
        "ALL_AIRCRAFT_LABELS_FROM_ZOOM = 9;",
        "ALL_AIRCRAFT_LABELS_FROM_ZOOM = 99;",
    ),
    "labels are placed in arrival order": (
        MAP,
        "[...candidates].sort((a, b) => a.rank - b.rank)",
        "[...candidates]",
    ),
    "labels may overlap": (
        MAP,
        "    if (kept.some((other) => overlaps(box, other))) continue;\n",
        "",
    ),
    "any icon hides any label": (MAP, "icon.rank <= candidate.rank", "true"),
    "anomalous receivers rank like the rest": (
        MAP,
        "rank: ANOMALOUS.has(sensor.health) ? 0 : 1,",
        "rank: 1,",
    ),
    # -- the map and the screen
    "satellite is offered unconfigured": (
        MAP,
        'status === "map" && satellite && (',
        'status === "map" && (',
    ),
    "the map starts on satellite": (
        MAP,
        DEFAULT_START,
        "style: satellite ? buildSatelliteStyle(satellite) : onThisOrigin(buildDefaultStyle(archive)),",
    ),
    "failing satellite falls back silently": (
        MAP,
        'if (basemapRef.current === "satellite") setSatelliteFailing(true);',
        'if (basemapRef.current === "satellite") map.setStyle(onThisOrigin(buildDefaultStyle(archive)));',
    ),
    "failing satellite is not stated": (
        MAP,
        "setSatelliteFailing(true);",
        "setSatelliteFailing(false);",
    ),
    "the worker URL is not set": (
        MAP,
        "      maplibre.setWorkerUrl(maplibreWorkerUrl);\n",
        "",
    ),
    "the map gets no aircraft": (
        SCREEN,
        "tracks={operationalPicture.aircraftTracks}",
        "tracks={[]}",
    ),
    "the placeholder comes back": (
        SCREEN,
        "<MapView sensors={operationalPicture.rfSensors} tracks={operationalPicture.aircraftTracks} zones={operationalPicture.interferenceZones} />",
        "<p>The map is not built yet. Receivers and aircraft are listed in the panel below.</p>",
    ),
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
