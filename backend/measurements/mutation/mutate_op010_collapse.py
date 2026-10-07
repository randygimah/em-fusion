"""Mutation pass over op-010's collapse: does a folded panel still count?

`op-010` is a screen item and the frontend has no coverage tooling, so this is
the only instrument that can say whether its 14 collapse tests hold anything up.

Three surfaces.

**What the folded header says.** The amendment's one constraint is that
collapsed, the header still states how many conclusions the hour holds and how
many have no stored evidence. Mutants drop the second count, pluralise one
conclusion, report a quiet hour as a count of zero, invent a count for an
unexamined hour, and say the same thing for a failed fetch as for one in flight.

**What the fold hides.** Mutants stop it hiding anything, report it open while
closed, and fold away the unclaimed-evidence note, which is a fact about the
hour whatever its conclusions look like.

**Where the preference lives.** Mutants open the panel collapsed by default,
resolve unreadable storage to collapsed, stop the preference persisting, accept
any stored value as "collapsed", and let a write failure escape.

Run: `python measurements/mutation/mutate_op010_collapse.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
PANEL = FRONTEND / "src/components/em/EmEvidencePanel.tsx"
HOOK = FRONTEND / "src/hooks/useEvidenceCollapsed.ts"
FILES = (PANEL, HOOK)
FRONTEND_TESTS = ["src/test/evidenceCollapse.test.tsx", "src/test/evidencePanel.test.tsx"]

M: dict[str, tuple[Path, str, str]] = {
    # -- what the folded header says
    "the no-evidence count is dropped": (
        PANEL,
        ' · ${account.unexplained.length} with no stored evidence`;',
        "`;",
    ),
    "one conclusion is pluralised": (
        PANEL,
        'conclusions === 1 ? "conclusion" : "conclusions"',
        '"conclusions"',
    ),
    "a quiet hour is reported as a count of zero": (
        PANEL,
        '  if (conclusions === 0) return "no conclusions";\n',
        "",
    ),
    "an unexamined hour says nothing distinct": (
        PANEL,
        'if (account === null) return "not examined";',
        'if (account === null) return "no conclusions";',
    ),
    "a failed fetch reads as one in flight": (
        PANEL,
        'if (account === "failed") return "could not be loaded";',
        'if (account === "failed") return "loading";',
    ),
    "the header shows no summary at all": (
        PANEL,
        "{summary(account)}",
        "{null}",
    ),
    # -- what the fold hides
    "the fold hides nothing": (
        PANEL,
        "hidden={collapsed}",
        "hidden={false}",
    ),
    "the control reports open while closed": (
        PANEL,
        "aria-expanded={!collapsed}",
        "aria-expanded={true}",
    ),
    "the unclaimed note folds away": (
        PANEL,
        '{typeof account === "object" &&\n        account !== null &&',
        '{!collapsed &&\n        typeof account === "object" &&\n        account !== null &&',
    ),
    # -- where the preference lives
    "it opens collapsed by default": (
        HOOK,
        "return window.localStorage.getItem(EVIDENCE_COLLAPSED_KEY) === COLLAPSED;",
        "return window.localStorage.getItem(EVIDENCE_COLLAPSED_KEY) !== EXPANDED;",
    ),
    "unreadable storage resolves to collapsed": (
        HOOK,
        "  } catch {\n    return false;\n  }",
        "  } catch {\n    return true;\n  }",
    ),
    "the preference is never saved": (
        HOOK,
        "      write(next);\n",
        "",
    ),
    "any stored value counts as collapsed": (
        HOOK,
        "=== COLLAPSED;",
        "!== null;",
    ),
    "a write failure escapes": (
        HOOK,
        '  try {\n    window.localStorage.setItem(EVIDENCE_COLLAPSED_KEY, collapsed ? COLLAPSED : EXPANDED);\n  } catch {\n    // A preference that cannot be saved lasts one visit. Not a failure to surface.\n  }\n',
        '  window.localStorage.setItem(EVIDENCE_COLLAPSED_KEY, collapsed ? COLLAPSED : EXPANDED);\n',
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
PANEL.write_text(ORIGINALS[PANEL].replace('aria-label="Evidence"', 'aria-label="Nothing"', 1))
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
