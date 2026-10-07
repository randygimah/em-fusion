"""Mutation pass over op-007: does the view filter's control hold the screen honest?

`op-007` is a screen item and the frontend has no coverage tooling, so this is
the only instrument that can say whether its 18 tests hold anything up.

Four surfaces.

**What is asked for.** Mutants open on `all` rather than Anomalous only, stop
sending the view, let the poll ignore it, wait for the next tick before asking
for a new one, and couple the view to the hour in either direction.

**What the rows are labelled.** Mutants name the rows by the control rather
than by the view they were served under, mark the served view rather than the
chosen one, mark nothing, and report no choice.

**What an emptied receiver grid says.** Mutants drop the sentence, count the
hidden receivers from the rows that arrived, call every hidden receiver
nominal, call an unexamined hour's hidden rows nominal, and drop the
not-examined sentence.

**What an emptied timeline says.** Mutants say "no events" while the view
withholds one, read an unexamined hour as quiet, and pluralise one conclusion.

Run: `python measurements/mutation/mutate_op007_view.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
WORDS = FRONTEND / "src/lib/viewVocabulary.ts"
HOOK = FRONTEND / "src/hooks/useOperationalPicture.ts"
API = FRONTEND / "src/lib/api.ts"
APP = FRONTEND / "src/App.tsx"
FILES = (SCREEN, WORDS, HOOK, API, APP)
FRONTEND_TESTS = [
    "src/test/viewFilter.test.tsx",
    "src/test/hourSelection.test.tsx",
    "src/test/operationalPicture.test.tsx",
    "src/test/dataAccess.test.tsx",
]

M: dict[str, tuple[Path, str, str]] = {
    # -- what is asked for
    "the default view is all": (WORDS, 'DEFAULT_VIEW: ViewSelection = "anomalous";', 'DEFAULT_VIEW: ViewSelection = "all";'),
    "the view is never sent": (API, '  params.set("view", view);\n', ""),
    "the poll ignores the view": (
        HOOK,
        "fetchOperationalPicture(baseUrl, runId, view)",
        "fetchOperationalPicture(baseUrl, runId)",
    ),
    "a new view waits for the next tick": (HOOK, "[runId, view, intervalMs, baseUrl]", "[runId, intervalMs, baseUrl]"),
    "choosing a view drops the pinned hour": (
        APP,
        "onSelectView={setView}",
        "onSelectView={(next) => { setView(next); setPinnedRun(null); }}",
    ),
    "pinning an hour resets the view": (
        APP,
        "onSelectHour={(runId) => setPinnedRun(Number.isNaN(runId) ? null : runId)}",
        "onSelectHour={(runId) => { setView(DEFAULT_VIEW); setPinnedRun(Number.isNaN(runId) ? null : runId); }}",
    ),
    # -- what the rows are labelled
    "rows are labelled by the control": (
        SCREEN,
        "{showingSentence(served.selected, selected)}",
        "{showingSentence(selected, selected)}",
    ),
    "the control marks the served view": (
        SCREEN,
        "const selected = selectedView ?? served.selected;",
        "const selected = served.selected;",
    ),
    "no option is marked": (SCREEN, "aria-checked={option.value === selected}", "aria-checked={false}"),
    "a choice is never reported": (
        SCREEN,
        "onClick={() => onSelectView?.(option.value)}",
        "onClick={() => undefined}",
    ),
    # -- what an emptied receiver grid says
    "an empty grid says nothing": (
        SCREEN,
        "{served.examined && operationalPicture.rfSensors.length === 0 && (",
        "{false && (",
    ),
    "the hidden count is counted from the rows": (
        SCREEN,
        "receiversHiddenSentence(served.selected, served.suppressed.rfSensors, served.examined)",
        "receiversHiddenSentence(served.selected, operationalPicture.rfSensors.length, served.examined)",
    ),
    "every hidden receiver is called nominal": (WORDS, 'view === "nominal" ? "out of nominal" : "nominal"', '"nominal"'),
    "an unexamined hour's hidden rows are called nominal": (
        WORDS,
        '  if (!examined) return `${hidden} ${hidden === 1 ? "receiver" : "receivers"} hidden by this view — choose All to see them.`;\n',
        "",
    ),
    "the grid drops the not-examined sentence": (
        SCREEN,
        '            {!served.examined && <p className="mt-4 text-sm text-[#ffb786]">{NOT_EXAMINED}</p>}\n',
        "",
    ),
    # -- what an emptied timeline says
    "no events while the view withholds one": (
        SCREEN,
        "operationalPicture.timelineEvents.length === 0 && served.suppressed.timelineEvents > 0 ? (",
        "false ? (",
    ),
    "an unexamined timeline reads as quiet": (SCREEN, "{!served.examined ? (", "{false ? ("),
    "one conclusion is pluralised": (WORDS, 'hidden === 1 ? "conclusion" : "conclusions"', '"conclusions"'),
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
SCREEN.write_text(ORIGINALS[SCREEN].replace('aria-label="View"', 'aria-label="Nothing"', 1))
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
