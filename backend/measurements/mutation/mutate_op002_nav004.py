"""Mutation pass over op-002 and nav-004: the rail's cards and each explanation's address.

The frontend has no coverage tooling, so this is the instrument that says
whether the op-002 tests (hypothesisCards.test.tsx) and the nav-004 tests
(hypothesisAddress.test.tsx) hold anything up, with the picture, navigation and
level suites run beside them.

**The words** (`lib/hypothesisVocabulary.ts`): a fallback read as an ordinary
card, the fallback naming the wrong arm, the model id dropped, the local model
misnamed, an unexamined hour read as zero conclusions, the singular lost, the
"no conclusions" sentence shown under explained cards, a positive count ignored.

**The cards** (`screens/operationalPicture.tsx`): a card linking to another
id, its status or provenance dropped, the sentence dropped, the old heading
back, a rejected card hidden.

**The address** (`routes.ts`, the hook, the seam, the placeholder): a leading
zero or trailing segment accepted, a malformed id sent to another screen, the
link built in another shape, the screen lookup ignoring ids, the id not handed
to the screen, the hook deaf to hash changes, the placeholder not naming it.

The badge and heading styling is not mutated: no test asserts a colour.

Run: `python measurements/mutation/mutate_op002_nav004.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
VOCAB = FRONTEND / "src/lib/hypothesisVocabulary.ts"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
ROUTES = FRONTEND / "src/routes.ts"
HOOK = FRONTEND / "src/hooks/useCurrentScreen.ts"
APP = FRONTEND / "src/App.tsx"
PLACEHOLDER = FRONTEND / "src/screens/hypotheses.tsx"
FILES = (VOCAB, SCREEN, ROUTES, HOOK, APP, PLACEHOLDER)
FRONTEND_TESTS = [
    "src/test/hypothesisCards.test.tsx",
    "src/test/hypothesisAddress.test.tsx",
    "src/test/pictureHypotheses.test.tsx",
    "src/test/navigation.test.tsx",
    "src/test/navCollapse.test.tsx",
    "src/test/operationalPicture.test.tsx",
    "src/test/levels.test.tsx",
    "src/test/dataAccess.test.tsx",
    "src/App.test.tsx",
]

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- the words
    "a fallback reads as an ordinary card": (VOCAB, [("  summary.fellBack\n    ? {", "  false\n    ? {")]),
    "the fallback names the wrong arm": (VOCAB, [("capitalise(WRITER[summary.requestedGenerator])", "capitalise(WRITER[summary.generator])")]),
    "the model id is dropped": (VOCAB, [('${summary.modelId === null ? "" : `, ${summary.modelId}`}', "")]),
    "the local model is misnamed": (VOCAB, [('local: "the local model"', 'local: "the AI model"')]),
    "an unexamined hour reads as zero": (VOCAB, [('if (count === null) return "This hour has not been examined";', 'if (count === null) return "No conclusions this hour";')]),
    "the singular is lost": (VOCAB, [("count === 1 ?", "count === 0 ?")]),
    "no-conclusions shown under explained cards": (VOCAB, [('explanations === 0 ? "No conclusions this hour" : null', '"No conclusions this hour"')]),
    "a positive count is ignored": (VOCAB, [("if (count > 0)", "if (count > 99)")]),
    # -- the cards
    "a card links to another id": (SCREEN, [("href={hypothesisHash(hypothesis.id)}", "href={hypothesisHash(hypothesis.bundleId)}")]),
    "the status is dropped": (SCREEN, [("                      {hypothesis.status}\n", "")]),
    "the provenance is dropped": (SCREEN, [(">{writer.text}</p>", "></p>")]),
    "the sentence is dropped": (SCREEN, [("unexplainedSentence(operationalPicture.unexplainedConclusions, operationalPicture.hypotheses.length)", "null")]),
    "the old heading is back": (SCREEN, [(">Hypotheses</h2>", ">Active Hypotheses</h2>")]),
    "a rejected card is hidden": (SCREEN, [("{operationalPicture.hypotheses.map((hypothesis) => {", '{operationalPicture.hypotheses.filter((h) => h.status !== "Rejected").map((hypothesis) => {')]),
    # -- the address
    "a leading zero is accepted": (ROUTES, [("([1-9][0-9]*)$/", "([0-9]+)$/")]),
    "a trailing segment is accepted": (ROUTES, [("([1-9][0-9]*)$/", "([1-9][0-9]*)/")]),
    "a malformed id goes to another screen": (
        ROUTES,
        [("    return { screen: hypotheses, hypothesisId: id === undefined ? null : Number(id) };", "    if (id === undefined) return { screen: DEFAULT_SCREEN, hypothesisId: null };\n    return { screen: hypotheses, hypothesisId: Number(id) };")],
    ),
    "the link is built in another shape": (ROUTES, [("`${HYPOTHESES_HASH}/${id}`", "`${HYPOTHESES_HASH}?id=${id}`")]),
    "the screen lookup ignores ids": (ROUTES, [("=> routeFromHash(hash).screen;", "=> SCREENS.find((screen) => screen.hash === hash) ?? DEFAULT_SCREEN;")]),
    "the id is not handed to the screen": (APP, [("<HypothesesScreen hypothesisId={current.hypothesisId} />", "<HypothesesScreen />")]),
    "the hook is deaf to hash changes": (HOOK, [('    window.addEventListener("hashchange", update);\n', "")]),
    "the placeholder does not name the id": (PLACEHOLDER, [("Asked for explanation {hypothesisId}.", "Asked for an explanation.")]),
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
VOCAB.write_text(ORIGINALS[VOCAB].replace('"This hour has not been examined"', '"x"', 1))
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
