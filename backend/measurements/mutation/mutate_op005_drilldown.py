"""Mutation pass over op-005: do the drill-down tables show all of one hour?

The frontend has no coverage tooling, so this is the instrument that says
whether the drill-down tests (30, plus the op-004 panel tests run beside them)
hold anything up.

**"All" means all.** The loader asks for a filtered view or for the newest hour,
an answer for another hour or another view is accepted, the table follows the
screen to a newer hour, the seam or the screen never hands the loader down.

**View all.** Always disabled, enabled with no hour, the two reasons swapped,
the wrong tab opened, focus not returned on closing.

**The table.** The heading without its count, the unfiltered sentence dropped,
the raw finding type served, an empty collection drawn as an empty table, the
not-examined sentence dropped.

**The order.** Direction ignored, no tie-break, an altitude not reported sorted
as zero, altitudes compared as text, Events opening on another column,
aria-sort never set.

**The find box.** Case-sensitive, the count against the matches rather than the
hour, no sentence when nothing matches.

**Loading, failing, closing.** No loading sentence, a retry that fetches
nothing, Escape ignored, the close button inert, the dialog not modal.

Run: `python measurements/mutation/mutate_op005_drilldown.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
DRILL = FRONTEND / "src/components/em/EmDrillDown.tsx"
PANEL = FRONTEND / "src/components/em/EmExceptionPanel.tsx"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
APP = FRONTEND / "src/App.tsx"
FILES = (DRILL, PANEL, SCREEN, APP)
FRONTEND_TESTS = [
    "src/test/drillDown.test.tsx",
    "src/test/exceptionPanel.test.tsx",
]

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- "all" means all
    "the loader asks for a filtered view": (
        APP,
        [('fetchOperationalPicture("", runId, "all")', 'fetchOperationalPicture("", runId, "anomalous")')],
    ),
    "the loader asks for the newest hour": (
        APP,
        [('fetchOperationalPicture("", runId, "all")', 'fetchOperationalPicture("", null, "all")')],
    ),
    "an answer for another hour is accepted": (DRILL, [("picture.scenario?.id === String(runId) && ", "")]),
    "a filtered answer is accepted": (DRILL, [(' && picture.view.selected === "all"', "")]),
    "the table follows the screen to a newer hour": (PANEL, [("runId={drill.runId}", "runId={hour ?? drill.runId}")]),
    "the seam hands down no loader": (APP, [("      loadUnfiltered={loadUnfiltered}\n", "")]),
    "the screen hands the panel no loader": (SCREEN, [("              loadUnfiltered={loadUnfiltered}\n", "")]),
    # -- View all
    "View all is always disabled": (PANEL, [("disabled={unavailable !== null}", "disabled")]),
    "View all is enabled with no hour": (
        PANEL,
        [(": hour === null ? NO_HOUR_TO_DRILL : null", ": null"), ("hour !== null && setDrill", "setDrill")],
    ),
    "the two reasons are swapped": (
        PANEL,
        [("!loadUnfiltered ? DRILL_DOWN_UNWIRED : hour === null ? NO_HOUR_TO_DRILL", "!loadUnfiltered ? NO_HOUR_TO_DRILL : hour === null ? DRILL_DOWN_UNWIRED")],
    ),
    "View all always opens the receivers": (PANEL, [("setDrill({ tab: open, runId: hour })", 'setDrill({ tab: "rf", runId: hour })')]),
    "focus is not returned on closing": (PANEL, [("            viewAllRef.current?.focus();\n", "")]),
    # -- the table
    "the heading has no count": (
        DRILL,
        [('loaded.status === "loaded" ? total(loaded.picture, tab) : null', "null")],
    ),
    "the unfiltered sentence is dropped": (DRILL, [('<p className="mt-1 text-xs text-[#8c909f]">{UNFILTERED}</p>', "")]),
    "a conclusion is served raw": (DRILL, [("render: (e) => findingLabel(e.event),", "render: (e) => e.event,")]),
    "an empty collection is an empty table": (DRILL, [("if (rows.length === 0) return", "if (false) return")]),
    "the not-examined sentence is dropped": (DRILL, [("{!examined && total(picture, tab) > 0 && ", "{false && ")]),
    # -- the order
    "the direction is ignored": (DRILL, [("return direction * (compare(a, b)", "return (compare(a, b)")]),
    "ties are left in array order": (DRILL, [("compare(a, b) || spec.identity(a, b)", "compare(a, b)")]),
    "an altitude not reported sorts as zero": (DRILL, [("    if (lastA !== lastB) return lastA ? 1 : -1;\n", "")]),
    "altitudes are compared as text": (
        DRILL,
        [("(a.altitudeFt ?? 0) - (b.altitudeFt ?? 0)", "byText(String(a.altitudeFt), String(b.altitudeFt))")],
    ),
    "Events open sorted by source": (DRILL, [("  initial: 0,", "  initial: 2,")]),
    "aria-sort is never set": (
        DRILL,
        [('aria-sort={sort.column === index ? (sort.direction === 1 ? "ascending" : "descending") : "none"}', 'aria-sort="none"')],
    ),
    # -- the find box
    "the find is case-sensitive": (DRILL, [("text.toLowerCase().includes(needle)", "text.includes(needle)")]),
    "the count is against the matches": (DRILL, [("shownCount(shown.length, rows.length)", "shownCount(shown.length, shown.length)")]),
    "nothing matching says nothing": (DRILL, [("{shown.length === 0 ? (", "{false ? (")]),
    # -- loading, failing, closing
    "loading says nothing": (
        DRILL,
        [('if (loaded.status === "loading") return <p className="p-4 text-sm text-[#c2c6d6]">{drillDownLoading(tab, runId)}</p>;', 'if (loaded.status === "loading") return null;')],
    ),
    "a retry fetches nothing": (DRILL, [("  }, [runId, attempt]);", "  }, [runId]);")]),
    "Escape is ignored": (DRILL, [('if (event.key !== "Escape") return;', 'if (event.key !== "Esc") return;')]),
    "the close button is inert": (DRILL, [("onClick={onClose}", "onClick={() => undefined}")]),
    "the dialog is not modal": (DRILL, [('        aria-modal="true"\n', "")]),
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
DRILL.write_text(ORIGINALS[DRILL].replace('role="dialog"', 'role="region"', 1))
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
