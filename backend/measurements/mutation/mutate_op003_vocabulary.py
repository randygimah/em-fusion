"""Mutation pass over op-003, op-006 and ui-001: the detection vocabulary.

Three items in one pass because the finding that shaped them is shared: the
detection summary and the timeline carry the SAME verbatim finding type, so the
copy is one module both panels read. A pass that scored them separately could
not see the thing that matters -- that the two panels agree.

**This pass has more to prove than the coverage gate could.** 18 of the 58
frontend tests passed against a raising stub, for reasons that establish
nothing: the non-numeric refusals have no digit to find, and a stub that renders
its label and a valid level satisfies those halves by accident. There is no
coverage tooling on that side of the project, so this is the only instrument
that can say whether those 18 hold anything up.

Four surfaces.

**The copy, and that there is one of it.** The mutants reinstate the raw token
in each panel separately, and -- the one worth having -- give the timeline its
own wording for a type the summary already words. That second mutant is the
whole reason these items were built together, and nothing but a test comparing
the two panels can kill it.

**The exhaustiveness guarantee.** A copy map that misses a member prints a
token, so the map's keys are the union and a parity test holds the union against
`anom-008`'s register. The mutants drop a member from the map, drop one from the
union, and loosen the fallback so an unmapped type prints itself.

**The level primitive's RUNTIME refusal.** The contract types these as
`Low|Medium|High`, so TypeScript refuses a number at the call site and sees
nothing -- the payload is cast from JSON. The mutants widen the accepted domain,
let the refused value render anyway, drop the label so the row goes silently
absent, remove the console error so the defect leaves no trace, and make the
primitive throw, which takes down a screen over one bad badge.

**The timeline's two orderings.** Events are instants in a replayed 2022 hour
and the run was generated in 2026, so a local or relative format states the
wrong thing (`anom-009`'s mistake). And the sort is a guard rather than a
correction: `api-012` already serves them oldest first, so a mutant removing the
sort is killed only by a test that supplies them out of order on purpose.

Run: `python measurements/mutation/mutate_op003_vocabulary.py` from `backend/`.
`SIDE=frontend` / `SIDE=backend` runs one half.
"""

import ast
import json
import os
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

CONTROL = BACKEND / "app/detection/control.py"
SCHEMA = BACKEND / "app/api/v1/schemas/operational_picture.py"
COPY = FRONTEND / "src/lib/detectionVocabulary.ts"
LEVEL = FRONTEND / "src/components/em/EmLevel.tsx"
SCREEN = FRONTEND / "src/screens/operationalPicture.tsx"
CONTRACT = FRONTEND / "src/types/operationalPicture.ts"

FILES = (CONTROL, SCHEMA, COPY, LEVEL, SCREEN, CONTRACT)

BACKEND_TESTS = [
    "tests/test_api_operational_picture.py",
    "tests/test_anom_control.py",
]
FRONTEND_TESTS = [
    "src/test/detectionVocabulary.test.tsx",
    "src/test/levels.test.tsx",
    "src/test/operationalPicture.test.tsx",
    "src/test/statusBar.test.tsx",
]

#: Which suite GUARDS a file, where its location implies the other one. The
#: TypeScript contract is held by `api-002`'s parity check, which parses that
#: file and lives in the backend suite because the parser exists once and on
#: that side. Dispatching on location alone scored such a mutant as a survivor
#: on the previous pass -- README.md's fifth hazard, second form.
GUARDED_BY: dict[Path, str] = {CONTRACT: "backend"}

#: name -> (file, anchor, replacement)
M: dict[str, tuple[Path, str, str]] = {
    # --- the copy, and that there is one of it -------------------------------
    "the summary prints the raw finding type again": (
        SCREEN,
        '<dt className="text-[#8c909f]">{findingLabel(entry.findingType)}</dt>',
        '<dt className="text-[#8c909f]">{entry.findingType}</dt>',
    ),
    "the timeline prints the raw finding type": (
        SCREEN,
        '<span className="text-[#e1e2ec]">{findingLabel(timelineEvent.event)}</span>',
        '<span className="text-[#e1e2ec]">{timelineEvent.event}</span>',
    ),
    "the timeline words a conclusion its own way": (
        SCREEN,
        '<span className="text-[#e1e2ec]">{findingLabel(timelineEvent.event)}</span>',
        '<span className="text-[#e1e2ec]">{`Event: ${timelineEvent.event.replace(/_/g, " ")}`}</span>',
    ),
    "a conclusion loses its wording and keeps its shape": (
        COPY,
        '  possible_sensor_fault: "Possible receiver fault",',
        '  possible_sensor_fault: "possible_sensor_fault",',
    ),
    "an unmapped type prints itself": (
        COPY,
        '  REPORTABLE_COPY[type as ReportableFindingType] ?? "Unrecognised finding type";',
        "  REPORTABLE_COPY[type as ReportableFindingType] ?? type;",
    ),
    "an unmapped type is dropped rather than named": (
        COPY,
        '  REPORTABLE_COPY[type as ReportableFindingType] ?? "Unrecognised finding type";',
        '  REPORTABLE_COPY[type as ReportableFindingType] ?? "";',
    ),
    # --- the closed set -----------------------------------------------------
    "the union loses a member the register declares": (
        CONTRACT,
        '  | "possible_data_source_issue";',
        "  ;",
    ),
    # Carries a background, because `Producer` refuses an intermediate producer
    # without one -- the first version of this mutant did not, so the module
    # raised on import and the suite reported errors rather than a failing
    # test. README.md's eighth hazard, met a second time: a mutation table over
    # a configuration module is also a table of things that must stay
    # CONSTRUCTIBLE, and the way to know is to construct each one first.
    "the register loses a reportable producer": (
        CONTROL,
        "    Producer(rule_id=FAULT_RULE, finding_type=FAULT_TYPE, kind=Kind.REPORTABLE),",
        "    Producer(\n"
        "        rule_id=FAULT_RULE,\n"
        "        finding_type=FAULT_TYPE,\n"
        "        kind=Kind.INTERMEDIATE,\n"
        "        background=Background(low=0, high=0, runs=60),\n"
        "    ),",
    ),
    # --- the level primitive's runtime refusal -------------------------------
    "any string counts as a level": (
        LEVEL,
        "  const valid = typeof value === \"string\" && ALLOWED.includes(value);",
        '  const valid = typeof value === "string";',
    ),
    "anything at all counts as a level": (
        LEVEL,
        "  const valid = typeof value === \"string\" && ALLOWED.includes(value);",
        "  const valid = true;",
    ),
    "a refused value renders anyway": (
        LEVEL,
        '      {valid && <dd className="font-mono text-[#4cd7f6]">{value}</dd>}',
        '      <dd className="font-mono text-[#4cd7f6]">{value}</dd>',
    ),
    "a refusal takes the label with it": (
        LEVEL,
        '      <dt className="text-[#c2c6d6]">{label}</dt>',
        '      {valid && <dt className="text-[#c2c6d6]">{label}</dt>}',
    ),
    "a refusal leaves no trace for the developer": (
        LEVEL,
        "  if (!valid) {\n    console.error(",
        "  if (false) {\n    console.error(",
    ),
    "the primitive throws rather than refusing": (
        LEVEL,
        "  if (!valid) {\n    console.error(",
        "  if (!valid) {\n    throw new Error(String(value));\n    console.error(",
    ),
    "the error no longer names the row it came from": (
        LEVEL,
        "      `${label}: refused a value outside Low|Medium|High",
        "      `refused a value outside Low|Medium|High",
    ),
    # --- the timeline's two orderings ---------------------------------------
    "the strip takes its order from the payload": (
        SCREEN,
        "                {oldestFirst(operationalPicture.timelineEvents).map((timelineEvent) => (",
        "                {operationalPicture.timelineEvents.map((timelineEvent) => (",
    ),
    "the strip orders newest first": (
        SCREEN,
        "  [...events].sort((a, b) => a.time.localeCompare(b.time));",
        "  [...events].sort((a, b) => b.time.localeCompare(a.time));",
    ),
    "the instant is formatted against the viewer's clock": (
        SCREEN,
        "const simulatedInstant = (iso: string): string => `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;",
        "const simulatedInstant = (iso: string): string => new Date(iso).toLocaleString();",
    ),
    "the instant loses its date and keeps the clock": (
        SCREEN,
        "const simulatedInstant = (iso: string): string => `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;",
        "const simulatedInstant = (iso: string): string => iso.slice(11, 16);",
    ),
    "an event loses the receiver it was claimed at": (
        SCREEN,
        '                    <span className="font-mono text-xs text-[#4cd7f6]">{timelineEvent.source}</span>',
        '                    <span className="font-mono text-xs text-[#4cd7f6]" />',
    ),
    "an empty strip says nothing": (
        SCREEN,
        "                No events in this hour. Nothing the detectors reported reached the analyst.",
        "                ",
    ),
    # --- what the panel may not count ---------------------------------------
    "intermediate findings are counted as anomalies": (
        SCREEN,
        '    (entry) => entry.kind === "reportable",',
        "    (entry) => true,",
    ),
    "a rule that does not exist is reported as zero": (
        SCREEN,
        '                      <dd className="font-mono">{entry.count ?? "—"}</dd>',
        '                      <dd className="font-mono">{entry.count ?? 0}</dd>',
    ),
}

EXPECTED_EQUIVALENT: dict[str, str] = {}

PYTEST_RAN = re.compile(r"(\d+) (?:passed|failed)")
VITEST_RAN = re.compile(r"Tests\s+\d+")
ORIGINALS = {path: path.read_text() for path in FILES}

SIDE = os.environ.get("SIDE", "both")
if SIDE not in {"both", "backend", "frontend"}:
    raise SystemExit(f"SIDE must be backend, frontend or both, not {SIDE!r}")


def _side_of(path: Path) -> str:
    located = "frontend" if FRONTEND in path.parents else "backend"
    return GUARDED_BY.get(path, located)


if SIDE != "both":
    M = {n: m for n, m in M.items() if _side_of(m[0]) == SIDE}

GUARD_FILE = Path(__file__).with_suffix(".in-progress.json")
if GUARD_FILE.exists():
    for name, text in json.loads(GUARD_FILE.read_text()).items():
        Path(name).write_text(text)
    GUARD_FILE.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. "
        "The originals have been put back from the guard file. Check `git diff` "
        "is clean, then run again."
    )
GUARD_FILE.write_text(json.dumps({str(p): t for p, t in ORIGINALS.items()}))


def _restore() -> None:
    for path, text in ORIGINALS.items():
        path.write_text(text)


def _backend_suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        [
            "make",
            "test-backend-nobuild",
            f"PYTEST_ARGS={' '.join(BACKEND_TESTS)} -q --no-cov",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    tail = [
        line
        for line in p.stdout.splitlines()
        if "passed" in line or "failed" in line or "error" in line
    ]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(PYTEST_RAN.search(summary))


def _frontend_suite() -> tuple[int, str, bool]:
    script = (
        'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null 2>&1; '
        "nvm use >/dev/null 2>&1; "
        f"pnpm exec vitest run {' '.join(FRONTEND_TESTS)}"
    )
    p = subprocess.run(
        ["bash", "-lc", script], cwd=str(FRONTEND), capture_output=True, text=True
    )
    both = p.stdout + p.stderr
    tail = [
        line.strip() for line in both.splitlines() if line.strip().startswith("Tests")
    ]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did vitest run?"
    return p.returncode, summary, bool(VITEST_RAN.search(summary))


def _suite_for(path: Path) -> tuple[int, str, bool]:
    return _frontend_suite() if _side_of(path) == "frontend" else _backend_suite()


for _label, _path, _from, _to, _run in (
    (
        "backend",
        SCHEMA,
        '            name=f"Run {run.id}",',
        '            name="",',
        _backend_suite,
    ),
    (
        "frontend",
        COPY,
        '  possible_interference_zone: "Possible interference across several receivers",',
        '  possible_interference_zone: "",',
        _frontend_suite,
    ),
):
    if SIDE not in {"both", _label}:
        continue
    assert ORIGINALS[_path].count(_from) == 1, (_label, _from)
    _path.write_text(ORIGINALS[_path].replace(_from, _to, 1))
    _code, _summary, _ran = _run()
    _restore()
    if not _ran:
        GUARD_FILE.unlink(missing_ok=True)
        raise SystemExit(f"the {_label} suite did not run at all: {_summary}")
    if not _code:
        GUARD_FILE.unlink(missing_ok=True)
        raise SystemExit(
            f"{_label.upper()} SENTINEL SURVIVED. A deliberately broken source "
            f"edit left that suite green ({_summary}), so edits are not "
            "reaching those tests."
        )
    print(f"{_label} sentinel killed ({_summary}) -- edits reach the tests", flush=True)
print(flush=True)

res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        original = ORIGINALS[path]
        if original.count(o) != 1:
            res[n] = f"INVALID ({original.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        mutated = original.replace(o, w, 1)
        if path.suffix == ".py":
            try:
                ast.parse(mutated)
            except SyntaxError as broken:
                res[n] = f"INVALID (does not parse: {broken.msg})"
                print(f"{n:62} {res[n]}", flush=True)
                continue
        if mutated == original:
            res[n] = "INVALID (identical to the original)"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        path.write_text(mutated)
        code, summary, ran = _suite_for(path)
        res[n] = (
            f"INCONCLUSIVE -- {summary}"
            if not ran
            else ("KILLED   " if code else "SURVIVED ") + summary
        )
        print(f"{n:62} {res[n]}", flush=True)
        _restore()
finally:
    _restore()
    GUARD_FILE.unlink(missing_ok=True)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
unclear = [n for n, v in res.items() if v.startswith("INCONCLUSIVE")]
print(f"\n{killed} killed of {len(res) - len(invalid) - len(unclear)} valid mutants")
if invalid:
    print(f"INVALID (anchor did not match once, or the mutant does not parse): {invalid}")
if unclear:
    print(f"INCONCLUSIVE (no test summary): {unclear}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
for n, why in EXPECTED_EQUIVALENT.items():
    if n in survived:
        print(f"\nEQUIVALENT as expected: {n}\n  {why}")
