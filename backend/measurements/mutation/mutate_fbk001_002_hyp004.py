"""Mutation pass over fbk-001, fbk-002 and hyp-004: the verdict card.

The frontend has no coverage tooling, so this is the instrument that says
whether the verdict card's tests (hypothesisVerdict.test.tsx) hold anything up,
with the screen's own suites and App.test beside them.

**What is shown after a verdict** (`screens/hypotheses.tsx`): the header, the
list or the sentence not taking the store's reply, a status worked out on
screen, another explanation's reply accepted, a failure silent, the history
showing the stored value.

**Sending**: the buttons live while sending or over the limit, the note cut to
fit, not sent, a blank one sent, kept after a recorded verdict, lost after a
failure; buttons on an explanation that takes no verdict; the card above the
map. (The first run's "card carried to another explanation", a removed `key`,
survived because a new address always unmounts the card through Loading; the
key was deleted as redundant.)

**The disclaimer** (hyp-004): dropped, reworded, only on the reviewable row,
hidden while sending, only a tooltip.

**The words and the wiring**: verdict words swapped, an unknown verdict blank,
the recorded sentence naming no status; in `lib/api.ts` the path, a refusal
read as success, the reply unchecked, the note or the content type dropped, the
limit raised; the seam posting for another explanation.

Styling is not mutated: no test asserts a colour or a column.

Run: `python measurements/mutation/mutate_fbk001_002_hyp004.py` from `backend/`.
"""

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
SCREEN = FRONTEND / "src/screens/hypotheses.tsx"
VOCAB = FRONTEND / "src/lib/hypothesisVocabulary.ts"
API = FRONTEND / "src/lib/api.ts"
APP = FRONTEND / "src/App.tsx"
FILES = (SCREEN, VOCAB, API, APP)
FRONTEND_TESTS = [
    "src/test/hypothesisVerdict.test.tsx",
    "src/test/hypothesisScreen.test.tsx",
    "src/test/hypothesisEvidence.test.tsx",
    "src/App.test.tsx",
]

CARD = """        <VerdictCard
          detail={detail}
          onRecorded={onRecorded}
          submitVerdict={submitVerdict}
        />
"""
DISCLAIMER = '<p className="mt-3 border-t border-[#424754] pt-3 text-xs text-[#c2c6d6]">{VERDICT_CARD_COPY.disclaimer}</p>'
CATCH = '.catch(() => setSending({ state: "failed" }));'
SENT = '{ verdict, note: note.trim() === "" ? null : note }'

#: name -> (file, [(old, new), ...]); every `old` must occur exactly once.
M: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    # -- what is shown after a verdict
    "the header keeps the loaded status": (SCREEN, [("detail={replies[hypothesisId] ?? detail.value}", "detail={detail.value}")]),
    "the list keeps the loaded status": (SCREEN, [("replies[hypothesis.id]?.status ?? hypothesis.status", "hypothesis.status")]),
    "a status worked out on screen": (SCREEN, [('setSending({ state: "recorded", status: reply.status });', 'setSending({ state: "recorded", status: "Confirmed" });')]),
    "another explanation's reply accepted": (SCREEN, [("        if (reply.id !== detail.id) throw new Error(`recorded a verdict on ${detail.id}, answered ${reply.id}`);\n", "")]),
    "a failure is silent": (SCREEN, [(CATCH, '.catch(() => setSending({ state: "idle" }));')]),
    "the history shows the stored value": (SCREEN, [("{verdictLabel(verdict.verdict)}", "{verdict.verdict}")]),
    # -- sending
    "the buttons live while sending": (SCREEN, [('const blocked = sending.state === "sending" || tooLong;', "const blocked = tooLong;")]),
    "an over-long note sent": (SCREEN, [('const blocked = sending.state === "sending" || tooLong;', 'const blocked = sending.state === "sending";')]),
    "the note cut to fit": (SCREEN, [("            rows={4}\n", "            maxLength={VERDICT_NOTE_LIMIT}\n            rows={4}\n")]),
    "the note not sent": (SCREEN, [(SENT, "{ verdict, note: null }")]),
    "a blank note sent as typed": (SCREEN, [(SENT, "{ verdict, note }")]),
    "the note kept after a recorded verdict": (SCREEN, [('        setNote("");\n', "")]),
    "the note lost after a failure": (SCREEN, [(CATCH, '.catch(() => {\n        setNote("");\n        setSending({ state: "failed" });\n      });')]),
    "buttons on an explanation that takes no verdict": (SCREEN, [("{detail.reviewable ? (", "{true ? (")]),
    "the card above the map": (SCREEN, [(CARD, ""), ("        <AffectedArea\n", CARD + "        <AffectedArea\n")]),
    # -- the disclaimer
    "the disclaimer dropped": (SCREEN, [(DISCLAIMER, "")]),
    "the disclaimer only on the reviewable row": (SCREEN, [(DISCLAIMER, "{detail.reviewable && " + DISCLAIMER + "}")]),
    "the disclaimer hidden while sending": (SCREEN, [("{VERDICT_CARD_COPY.disclaimer}", '{sending.state === "sending" ? null : VERDICT_CARD_COPY.disclaimer}')]),
    "the disclaimer only a tooltip": (SCREEN, [(DISCLAIMER, '<p className="mt-3" title={VERDICT_CARD_COPY.disclaimer} />')]),
    "the disclaimer reworded": (VOCAB, [('disclaimer: "Decision support only — analyst judgement is final."', 'disclaimer: "Decision support only."')]),
    # -- the words and the wiring
    "verdict words swapped": (VOCAB, [('  confirm: "Confirm",\n  reject: "Reject",', '  confirm: "Reject",\n  reject: "Confirm",')]),
    "an unknown verdict blank": (VOCAB, [('?? "Unrecognised verdict"', '?? ""')]),
    "the recorded sentence names no status": (VOCAB, [("recorded: (status: ReviewStatus) => `Verdict recorded. The status is now ${status}.`", "recorded: (_status: ReviewStatus) => `Verdict recorded.`")]),
    "the verdict posted to the detail's path": (API, [("const path = `${HYPOTHESES_PATH}/${id}/feedback`;", "const path = `${HYPOTHESES_PATH}/${id}`;")]),
    "a refusal read as success": (API, [("    body: JSON.stringify(request),\n  });\n  if (!response.ok) {", "    body: JSON.stringify(request),\n  });\n  if (false) {")]),
    "the reply not checked": (API, [('if (typeof payload?.id !== "number" || !Array.isArray(payload?.verdicts)) {', "if (false) {")]),
    "the note dropped from the body": (API, [("body: JSON.stringify(request),", "body: JSON.stringify({ verdict: request.verdict }),")]),
    "no JSON content type": (API, [('    headers: { "Content-Type": "application/json" },\n    body: JSON.stringify(request),', "    body: JSON.stringify(request),")]),
    "the limit raised": (API, [("export const VERDICT_NOTE_LIMIT = 2000;", "export const VERDICT_NOTE_LIMIT = 2001;")]),
    "the seam posts for another explanation": (APP, [("postVerdict(id, request)", "postVerdict(id + 1, request)")]),
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
VOCAB.write_text(ORIGINALS[VOCAB].replace('sending: "Recording the verdict."', 'sending: "x"', 1))
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
