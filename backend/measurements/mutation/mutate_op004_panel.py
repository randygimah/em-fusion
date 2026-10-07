"""Mutation pass over op-004: does the exception panel say what it shows?

`op-004` is a screen item and the frontend has no coverage tooling, so this is
the only instrument that can say whether its 22 tests -- and the 13 `op-006`
and `op-007` tests re-pointed at its tabs -- hold anything up.

Four surfaces.

**The tab labels.** Mutants call every out-of-nominal row by the anomalous word
whatever the view, give an unexamined hour's tabs a state word, give All's tabs
one, call interrupted aircraft anomalous, and count rows the tab does not show.

**The footer.** Mutants call an unexamined hour's withheld rows nominal, call
what Nominal only withheld nominal, report "+0" instead of saying the view hides
nothing, pluralise one conclusion, count withheld rows from the rows that
arrived, and enable View all.

**An empty tab.** Mutants render an empty table instead of a sentence, drop the
not-examined sentence, say a quiet hour where Nominal only withheld the
conclusions, and blur what an empty Tracks tab found.

**Rows and the open tab.** Mutants print a dash for a missing altitude, stop
ordering events by time, invent a Severity column, open on Tracks, mark every
tab selected, and key the panel on the run so a new hour resets the open tab.

Run: `python measurements/mutation/mutate_op004_panel.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
PANEL = FRONTEND / "src/components/em/EmExceptionPanel.tsx"
WORDS = FRONTEND / "src/lib/viewVocabulary.ts"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
FILES = (PANEL, WORDS, SCREEN)
FRONTEND_TESTS = [
    "src/test/exceptionPanel.test.tsx",
    "src/test/viewFilter.test.tsx",
    "src/test/detectionVocabulary.test.tsx",
    "src/test/operationalPicture.test.tsx",
]

M: dict[str, tuple[Path, str, str]] = {
    # -- the tab labels
    "the label word ignores the view": (
        WORDS,
        '${view === "anomalous" ? ANOMALOUS_WORD[tab] : "nominal"})`',
        "${ANOMALOUS_WORD[tab]})`",
    ),
    "an unexamined hour's tabs carry a state": (
        WORDS,
        'if (tab === "events" || !examined || view === "all")',
        'if (tab === "events" || view === "all")',
    ),
    "All's tabs carry a state": (
        WORDS,
        'if (tab === "events" || !examined || view === "all")',
        'if (tab === "events" || !examined)',
    ),
    "interrupted aircraft are called anomalous": (WORDS, 'tracks: "interrupted" }', 'tracks: "anomalous" }'),
    "a tab counts rows it does not show": (
        PANEL,
        "    rf: picture.rfSensors.length,\n",
        "    rf: picture.rfSensors.length + suppressed.rfSensors,\n",
    ),
    # -- the footer
    "an unexamined hour's withheld rows are called nominal": (WORDS, "  if (!examined) {", "  if (false) {"),
    "what Nominal only withheld is called nominal": (
        WORDS,
        '${view === "nominal" ? ANOMALOUS_WORD[tab] : "nominal"} hidden',
        "nominal hidden",
    ),
    "nothing withheld reads +0": (WORDS, '  if (hidden === 0) return "This view hides nothing.";\n', ""),
    "one conclusion is pluralised": (WORDS, 'plural(hidden, "conclusion", "conclusions")', '"conclusions"'),
    "withheld rows are counted from the rows that arrived": (
        PANEL,
        "    rf: suppressed.rfSensors,\n",
        "    rf: picture.rfSensors.length,\n",
    ),
    "View all is enabled": (PANEL, "              disabled\n", ""),
    # -- an empty tab
    "an empty tab renders an empty table": (PANEL, "if (shown[tab] === 0) return", "if (false) return"),
    "an empty tab drops the not-examined sentence": (PANEL, "    if (!examined) return NOT_EXAMINED;\n", ""),
    "a withheld conclusion reads as a quiet hour": (
        PANEL,
        "hidden.events > 0 ? EVENTS_ARE_ANOMALOUS : QUIET_HOUR",
        "QUIET_HOUR",
    ),
    "an empty Tracks tab blurs what it found": (WORDS, '"No aircraft\'s reporting broke."', '"No aircraft."'),
    # -- rows and the open tab
    "a missing altitude is a dash": (PANEL, 'feet === null ? "not reported"', 'feet === null ? "—"'),
    "events follow array order": (
        PANEL,
        "[...events].sort((a, b) => a.time.localeCompare(b.time))",
        "[...events]",
    ),
    "an invented Severity column": (
        PANEL,
        "<th className={headCell}>Band</th>",
        "<th className={headCell}>Band</th><th className={headCell}>Severity</th>",
    ),
    "it opens on Tracks": (PANEL, 'useState<ExceptionTab>("rf")', 'useState<ExceptionTab>("tracks")'),
    "every tab is marked selected": (PANEL, "aria-selected={tab === open}", "aria-selected={true}"),
    "a new hour resets the open tab": (
        SCREEN,
        "<EmExceptionPanel picture={operationalPicture} />",
        '<EmExceptionPanel key={operationalPicture.scenario?.id ?? ""} picture={operationalPicture} />',
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
    p = subprocess.run(["bash", "-lc", script], cwd=str(FRONTEND), capture_output=True, text=True)
    lines = [ln.strip() for ln in (p.stdout + p.stderr).splitlines() if ln.strip().startswith("Tests")]
    summary = lines[-1] if lines else "NO TEST SUMMARY -- did vitest run?"
    return p.returncode, summary, bool(VITEST_RAN.search(summary))


# Sentinel: a deliberately broken edit must turn the suite red, or edits are not
# reaching the tests and every "killed" below would be meaningless.
PANEL.write_text(ORIGINALS[PANEL].replace('aria-label="Exceptions"', 'aria-label="Nothing"', 1))
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
                f"INCONCLUSIVE -- {summary}" if not ran
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
