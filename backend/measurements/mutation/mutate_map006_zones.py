"""Mutation pass over map-006: does the map draw interference zones as specified?

The frontend has no coverage tooling, so this is the instrument that says
whether the zone tests (13 on the adapter, 1 on the boundary) hold anything up.
MapLibre needs WebGL, which jsdom lacks, so the disc is checked through what the
adapter hands the library -- the source's features and the layers' paint.

**The disc.** The wrong radius, a circle in degrees rather than on the sphere,
too few vertices, an open ring, a disc drawn with no recorded radius, the disc
in the markers' orange, the dash or the fill dropped, never drawn on load, lost on a basemap switch, left stale
when the zones change, a disc that takes clicks, no source at all when there
are no zones.

**The centre marker and label.** The confidence or the receivers dropped from
the name, the marker at latitude-first, the label reworded or outranked.

**The pop-up.** Receivers, window, confidence or corroboration dropped or
served raw, the assessed-area sentence missing, the no-radius sentence replaced
by a radius.

**The vocabulary and the screen.** Two corroborations worded alike; the screen
not handing the map its zones.

**Not mutated: the basemap switch's `diff: false`.** Without it MapLibre diffs
the styles, fires no `style.load` and drops the zone source, so the disc
vanishes. The fake map has no diff semantics, so no unit test can observe it;
the reasoning is from MapLibre's own `setStyle` source and is recorded on the
call.

Run: `python measurements/mutation/mutate_map006_zones.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
MAP = FRONTEND / "src/components/map/MapView.tsx"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
VOCAB = FRONTEND / "src/lib/detectionVocabulary.ts"
FILES = (MAP, SCREEN, VOCAB)
FRONTEND_TESTS = [
    "src/test/mapView.test.tsx",
    "src/test/mapBoundary.test.tsx",
]

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- the disc
    "the radius is halved": (
        MAP,
        [("const angular = radiusKm / EARTH_RADIUS_KM;", "const angular = radiusKm / EARTH_RADIUS_KM / 2;")],
    ),
    "the circle ignores latitude": (
        MAP,
        [("Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1)", "Math.sin(bearing) * Math.sin(angular)")],
    ),
    "the circle has eight vertices": (MAP, [("steps = 64", "steps = 8")]),
    "the ring is left open": (MAP, [("  ring.push(ring[0]);\n", "")]),
    "a disc is drawn with no recorded radius": (
        MAP,
        [
            ("    zone.radiusKm === null\n      ? []", "    false\n      ? []"),
            ("zoneOutline(zone.centre, zone.radiusKm)", "zoneOutline(zone.centre, zone.radiusKm ?? 60)"),
        ],
    ),
    "the disc is drawn in the anomalous orange": (
        MAP,
        [('const ZONE_COLOUR = "#93000a";', 'const ZONE_COLOUR = "#df7412";')],
    ),
    "the outline is not dashed": (MAP, [(', "line-dasharray": [3, 2]', "")]),
    "the fill is dropped": (
        MAP,
        [('  { id: "zones-fill", type: "fill", source: ZONE_SOURCE, paint: { "fill-color": ZONE_COLOUR, "fill-opacity": 0.08 } },\n', "")],
    ),
    "the disc is not drawn on load": (MAP, [('      map.on("load", drawZones);\n', "")]),
    "the disc is lost on a basemap switch": (MAP, [('      map.on("style.load", drawZones);\n', "")]),
    # Re-pointed by map-004: `source.setData(data)` now also updates the trails.
    "the disc is not updated when the zones change": (
        MAP,
        [("    const data = zoneDiscs(zonesRef.current);\n    const source = map.getSource(ZONE_SOURCE) as GeoJSONSource | undefined;\n    if (source) {\n      source.setData(data);\n", "    const data = zoneDiscs(zonesRef.current);\n    const source = map.getSource(ZONE_SOURCE) as GeoJSONSource | undefined;\n    if (source) {\n")],
    ),
    "the disc takes clicks": (
        MAP,
        [
            (
                "    for (const layer of ZONE_LAYERS) map.addLayer(layer);\n",
                "    for (const layer of ZONE_LAYERS) map.addLayer(layer);\n"
                '    map.on("click", "zones-fill", () => setSelected(null));\n',
            )
        ],
    ),
    "no source when there are no zones": (
        MAP,
        [
            (
                "    if (!map) return;\n    const data = zoneDiscs(",
                "    if (!map || zonesRef.current.length === 0) return;\n    const data = zoneDiscs(",
            )
        ],
    ),
    # -- the centre marker and label
    "the marker's name drops the confidence": (MAP, [(", ${zone.confidence} confidence`", "`")]),
    "the marker's name lists receivers with commas only": (
        MAP,
        [("over ${listed(zone.receivers)}", "over ${zone.receivers.join(\", \")}")],
    ),
    "the marker sits latitude first": (
        MAP,
        [
            (
                "        lat: zone.centre.lat,\n        lon: zone.centre.lon,",
                "        lat: zone.centre.lon,\n        lon: zone.centre.lat,",
            )
        ],
    ),
    "the zone's label ranks like an aircraft": (MAP, [("        rank: -1,", "        rank: 3,")]),
    "the zone's label is reworded": (
        MAP,
        [("`Possible interference · ${entity.zone.confidence}`", "`Interference · ${entity.zone.confidence}`")],
    ),
    # -- the pop-up
    "the receivers row is dropped": (MAP, [('          ["Receivers", zone.receivers.join(", ")],\n', "")]),
    "the window is the raw start": (MAP, [('["Window", zoneWindow(zone)]', '["Window", zone.startedAt]')]),
    "the confidence row is dropped": (MAP, [('          ["Confidence", zone.confidence],\n', "")]),
    "the corroboration is served raw": (
        MAP,
        [("corroborationLabel(zone.corroboration)", "zone.corroboration")],
    ),
    "the assessed-area sentence is missing": (
        MAP,
        [
            (
                ": `The circle is the ${popup.zone.radiusKm} km area the rule assessed, not a measured extent of the interference.`",
                ': ""',
            )
        ],
    ),
    "a missing radius is worded as one": (MAP, [("{popup.zone.radiusKm === null", "{false")]),
    # -- the vocabulary and the screen
    "two corroborations are worded alike": (
        VOCAB,
        [
            (
                '  not_corroborated: "Aircraft reporting in the area was measured and not disrupted beyond normal",',
                '  not_corroborated: "Aircraft reporting in the area was disrupted beyond normal, which supports it",',
            )
        ],
    ),
    # Re-pointed by map-004: the screen hands the map `mapZones`.
    "the map gets no zones": (SCREEN, [("                zones={mapZones}\n", "")]),
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
