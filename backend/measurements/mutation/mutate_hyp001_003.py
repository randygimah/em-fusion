"""Mutation pass over hyp-001, hyp-002 and hyp-003: the Hypotheses screen.

The frontend has no coverage tooling, so this is the instrument that says
whether the screen's tests (hypothesisScreen.test.tsx, hypothesisEvidence.test.tsx)
hold anything up, with the map, card, address and navigation suites beside them.

**Loading** (`screens/hypotheses.tsx`): a slow answer kept, the previous
explanation shown under a new address, another id's answer accepted, a 404
read as a failure, the conclusion's hour not the one asked for.

**The list**: the open entry unmarked, a link to the bundle, the unreviewable
count dropped.

**The detail**: provenance dropped, the verdict history hidden, a failing
citation hidden or marked grounded, citations out of order, the stored check
dropped, the two doubt sections merged, an empty one silent.

**The map**: a fault read as an area, every receiver drawn, the bounds or the
radius ignored, a missing radius or a failed map silent; and in
`lib/affectedArea.ts` the disc, the points, the margin, the longitude scale,
and the zone match (two matches, order, window, instants, set size).

**The words and the wiring**: not checked read as passed, the two failures
worded alike, an unrecognised check blank, the window's end or the centre's
precision lost; the 404 and both payload checks in `lib/api.ts`; the seam's
loaders; MapView's bounds.

Styling is not mutated: no test asserts a colour or a column.

Run: `python measurements/mutation/mutate_hyp001_003.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
SCREEN = FRONTEND / "src/screens/hypotheses.tsx"
VOCAB = FRONTEND / "src/lib/hypothesisVocabulary.ts"
AREA = FRONTEND / "src/lib/affectedArea.ts"
API = FRONTEND / "src/lib/api.ts"
APP = FRONTEND / "src/App.tsx"
MAP = FRONTEND / "src/components/map/MapView.tsx"
FILES = (SCREEN, VOCAB, AREA, API, APP, MAP)
FRONTEND_TESTS = [
    "src/test/hypothesisScreen.test.tsx",
    "src/test/hypothesisEvidence.test.tsx",
    "src/test/hypothesisCards.test.tsx",
    "src/test/hypothesisAddress.test.tsx",
    "src/test/mapView.test.tsx",
    "src/test/navigation.test.tsx",
    "src/test/navCollapse.test.tsx",
    "src/App.test.tsx",
]

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- loading
    "a slow answer is kept": (SCREEN, [("(value) => live && setHeld(", "(value) => setHeld(")]),
    "the previous explanation shows under a new address": (SCREEN, [("held?.key === key ? held.outcome", "held ? held.outcome")]),
    "another id's answer is accepted": (SCREEN, [("if (answer.id !== hypothesisId) throw", "if (false) throw")]),
    "a 404 reads as a failure": (SCREEN, [("{detail.error instanceof HypothesisNotFoundError ? SCREEN_COPY.notFound", "{false ? SCREEN_COPY.notFound")]),
    "the map asks for another hour": (SCREEN, [("() => loadPicture(runId as number)", "() => loadPicture(0)")]),
    # -- the list
    "the open entry is not marked": (SCREEN, [('aria-current={hypothesis.id === openId ? "page" : undefined}', "aria-current={undefined}")]),
    "an entry links to its bundle": (SCREEN, [("href={hypothesisHash(hypothesis.id)}", "href={hypothesisHash(hypothesis.bundleId)}")]),
    "the unreviewable count is dropped": (SCREEN, [("{list.value.unreviewableBundles > 0 &&", "{false &&")]),
    # -- the detail
    "the provenance is dropped": (SCREEN, [(">{writer.text}</p>", "></p>")]),
    "the verdict history is hidden": (SCREEN, [("{detail.verdicts.length === 0 ? (", "{true ? (")]),
    "a failing citation is hidden": (SCREEN, [("{citations.map((citation) => {", '{citations.filter((c) => c.grounding === "grounded").map((citation) => {')]),
    "a failing citation reads grounded": (SCREEN, [("{grounded ? CITATION_GROUNDING_COPY.grounded : citationGroundingLabel(citation.grounding)}", "{CITATION_GROUNDING_COPY.grounded}")]),
    "citations are out of order": (SCREEN, [(".sort((a, b) => a.position - b.position)", ".sort(() => 0)")]),
    "the stored check is dropped": (SCREEN, [('{STORED_GROUNDING_COPY[detail.grounding] ?? "Unrecognised check result"}', "{null}")]),
    "the doubts are merged": (SCREEN, [("<Sentences sentences={detail.evidenceAgainstOrUncertainty} />", "<Sentences sentences={[...detail.evidenceAgainstOrUncertainty, ...detail.alternativeExplanations]} />")]),
    "an empty doubt section is silent": (SCREEN, [('<p className={cn(NOTE, "mt-3")}>{SCREEN_COPY.noneRecorded}</p>', "null")]),
    # -- the map
    "a fault reads as an area": (SCREEN, [('const interference = bundle.anomalyType === "possible_interference_zone";', "const interference = true;")]),
    "every receiver is drawn": (SCREEN, [("picture.value.rfSensors.filter((sensor) => bundle.receivers.includes(sensor.id))", "picture.value.rfSensors")]),
    "the bounds are not handed over": (SCREEN, [("bounds={affectedAreaBounds(", "data-bounds={affectedAreaBounds(")]),
    "the radius is ignored": (SCREEN, [("zone?.radiusKm ?? null", "null")]),
    "a missing radius is silent": (SCREEN, [("? SCREEN_COPY.noRadius", "? null")]),
    "a failed map is silent": (SCREEN, [('body = <p className="mt-3 text-sm text-[#ffb4ab]">{SCREEN_COPY.mapFailed}</p>;', "body = null;")]),
    "the disc is not fitted": (AREA, [("Math.max(radiusKm ?? 0, MARGIN_KM)", "MARGIN_KM")]),
    "the named points are ignored": (AREA, [(", ...points.flatMap((point) => box(point, MARGIN_KM))", "")]),
    "no margin round a point": (AREA, [("const MARGIN_KM = 10;", "const MARGIN_KM = 0;")]),
    "longitude is not scaled by latitude": (AREA, [("(KM_PER_DEGREE * Math.cos((lat * Math.PI) / 180))", "KM_PER_DEGREE")]),
    "two matching zones choose the first": (AREA, [("matches.length === 1 ? matches[0] : null", "matches[0] ?? null")]),
    "receivers match as a sequence": (AREA, [("zone.receivers.every((receiver) => named.has(receiver))", "zone.receivers.every((receiver, i) => receiver === conclusion.receivers[i])")]),
    "the window is not compared": (AREA, [("sameInstant(zone.startedAt, conclusion.windowStart) &&", "")]),
    "instants compare as strings": (AREA, [("Date.parse(a) === Date.parse(b)", "a === b")]),
    "a subset of receivers matches": (AREA, [("new Set(zone.receivers).size === named.size &&", "")]),
    # -- the words
    "not checked reads as passed": (VOCAB, [('not_checked: "Not checked against the evidence when written"', 'not_checked: "Checked when written: every citation found in the evidence"')]),
    "the two failures are worded alike": (VOCAB, [('superseded: "Cites a claim the rules set aside"', 'superseded: "Not found in the evidence"')]),
    "an unrecognised check is blank": (VOCAB, [('?? "Unrecognised check result";', '?? "";')]),
    "the window's end is lost": (VOCAB, [("–${clockLabel(Date.parse(end))}", "–${clockLabel(Date.parse(start))}")]),
    "the centre loses precision": (VOCAB, [("${Math.abs(lat).toFixed(3)}", "${Math.abs(lat).toFixed(2)}")]),
    # -- the wiring
    "a 404 is not told apart": (API, [("  if (response.status === 404) throw new HypothesisNotFoundError(id);\n", "")]),
    "the list answer is not checked": (API, [("if (!Array.isArray(payload?.hypotheses)) {", "if (false) {")]),
    "the detail answer is not checked": (API, [('if (typeof payload?.id !== "number" || !Array.isArray(payload?.supportingEvidence)) {', "if (false) {")]),
    "the seam asks for another explanation": (APP, [("fetchHypothesis(id);", "fetchHypothesis(id + 1);")]),
    "the conclusion's hour is fetched filtered": (APP, [('const loadConclusionHour = (runId: number) => fetchOperationalPicture("", runId, "all");', 'const loadConclusionHour = (runId: number) => fetchOperationalPicture("", runId, "anomalous");')]),
    "MapView ignores its bounds": (MAP, [("          // Read once: a screen showing other bounds mounts another map.\n          bounds,", "          bounds: CORPUS_BOUNDS,")]),
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
VOCAB.write_text(ORIGINALS[VOCAB].replace('noneRecorded: "None recorded"', 'noneRecorded: "x"', 1))
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
