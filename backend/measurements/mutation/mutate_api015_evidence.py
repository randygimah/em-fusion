"""Mutation pass over db-011, api-015, op-010 and evb-003: the screen says why.

Four items in one pass because they are one capability, and because the
guarantee that matters spans all four: an account of **every** reported claim
and **every** stored bundle, with nothing dropped in either direction. A pass
scoring them separately could not see a mutant that drops a row on one side,
which is exactly the failure the two-sided completeness rule exists to prevent.

**This pass has more to prove on the frontend half than coverage can.**
`op-010` is a screen item and there is no coverage tooling on that side, so
this is the only instrument that can say whether its 29 tests hold anything up.

Five surfaces.

**The cascade (`db-011`).** The one unguarded data-loss path this session
found: the bundle write replaces per run, `hypotheses.bundle_id` cascades on
delete and is that table's only link to a run, and 155 rows on the store of
record hang off 20 bundles. The mutants switch the refusal off, skip it for an
empty write (the worst case, since clearing a cited run is the same cascade
with nothing inserted afterwards), widen it to the whole store so every
regeneration is refused, let it run after resolution, and strip the counts from
the message that tells a reader a protected population from a bug.

**The match key (`api-015`).** There is no column joining a bundle to its
conclusion, so they are matched on fields, and the key took two corrections.
The mutants put the raw subject back -- which misses all 41 interference
bundles while matching every fault, a defect that looks like a feature on half
a corpus -- and resolve an ambiguous key by taking the first row, which is the
unordered-result failure this repository has recorded three times.

**What may not be dropped (`api-015`).** Mutants drop the unclaimed list, admit
intermediate findings as conclusions, and group on the rule alone -- which
collapses the rate excess into the discontinuities it is derived from, the
fourth place that collision has had to be handled.

**What may not be computed (`api-015`, `op-010`).** The endpoint re-organises
and computes nothing beyond a count of the items a group lists. Mutants take a
group's span from the first item rather than the earliest, fix a count at one,
and stop identical absences collapsing -- the last being the defect found by
looking at the running screen, where real bundles repeat a single sentence up
to 28 times.

**The four states the panel keeps apart (`op-010`).** No answer, the server
saying no pass examined this hour, a quiet hour, and a claim with no evidence.
Mutants conflate the first two -- reporting a transport failure as a fact about
the store -- render a judgement indistinguishably from a measurement, collapse
the three absence kinds, truncate a statement, and let a failed fetch keep the
previous hour's evidence on screen under this hour's conclusion.

Run: `python measurements/mutation/mutate_api015_evidence.py` from `backend/`.
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

BUNDLES = BACKEND / "app/db/bundles.py"
EVIDENCE = BACKEND / "app/api/v1/schemas/evidence.py"
CHAIN = BACKEND / "app/detection/chain.py"
PANEL = FRONTEND / "src/components/em/EmEvidencePanel.tsx"
HOOK = FRONTEND / "src/hooks/useEvidenceAccount.ts"
API = FRONTEND / "src/lib/api.ts"
CONTRACT = FRONTEND / "src/types/evidence.ts"

FILES = (BUNDLES, EVIDENCE, CHAIN, PANEL, HOOK, API, CONTRACT)

BACKEND_TESTS = [
    "tests/test_db_cited_bundles.py",
    "tests/test_api_evidence.py",
    "tests/test_evb_persisted.py",
    "tests/test_anom_chain.py",
]
FRONTEND_TESTS = [
    "src/test/evidencePanel.test.tsx",
    "src/test/evidenceAccess.test.tsx",
]

#: Which suite GUARDS a file, where its location implies the other one. The
#: TypeScript contract is held by `op-010`'s parity check, which parses that
#: file and lives in the backend suite because the parser exists once and on
#: that side. Dispatching on location alone scored such a mutant as a survivor
#: on an earlier pass -- README.md's fifth hazard, second form.
GUARDED_BY: dict[Path, str] = {CONTRACT: "backend"}

#: name -> (file, anchor, replacement)
M: dict[str, tuple[Path, str, str]] = {
    # --- the cascade (db-011) ------------------------------------------------
    "a cited run's bundles are replaced after all": (
        BUNDLES,
        "    if not cited:\n        return",
        "    if True:\n        return",
    ),
    "clearing a cited run is allowed": (
        BUNDLES,
        "    _refuse_if_cited(session_factory, scenario_run_id)",
        "    if bundles:\n        _refuse_if_cited(session_factory, scenario_run_id)",
    ),
    "the guard asks whether anything cites anything": (
        BUNDLES,
        '                    "WHERE b.scenario_run_id = :run "',
        '                    "WHERE :run IS NOT NULL "',
    ),
    "the refusal happens after every citation is resolved": (
        BUNDLES,
        "    _refuse_if_cited(session_factory, scenario_run_id)\n\n    resolved = resolve_bundles(session_factory, bundles)",
        "    resolved = resolve_bundles(session_factory, bundles)\n    _refuse_if_cited(session_factory, scenario_run_id)",
    ),
    "the refusal no longer prints what it is protecting": (
        BUNDLES,
        '        f"{total} hypothes{rows} cite {len(cited)} of them ({names}). The "',
        '        "some hypotheses cite some of them. The "',
    ),
    # --- the match key (api-015) --------------------------------------------
    "the key uses the subject as the bundle stores it": (
        EVIDENCE,
        "            _head(bundle.subject),",
        "            bundle.subject,",
    ),
    "an ambiguous key is resolved by taking the first": (
        EVIDENCE,
        "        if key in by_key:",
        "        if False:",
    ),
    "two claims of one identity are both served": (
        EVIDENCE,
        "        if key in seen:",
        "        if False:",
    ),
    # --- what may not be dropped (api-015) ----------------------------------
    "stored evidence matching no claim is dropped": (
        EVIDENCE,
        "        for key, (bundle_id, bundle) in by_key.items()\n        if key not in matched",
        "        for key, (bundle_id, bundle) in by_key.items()\n        if False",
    ),
    "intermediate findings are accounted as conclusions": (
        EVIDENCE,
        "        if (finding.rule_id, finding.finding_type) not in reportable:",
        "        if False:",
    ),
    "evidence is grouped on the rule alone": (
        EVIDENCE,
        "        pair: Key = (item.rule_id, item.finding_type)",
        "        pair: Key = (item.rule_id, item.rule_id)",
    ),
    "a group spanning two groundings is served anyway": (
        EVIDENCE,
        "    if len(distinct) != 1:",
        "    if False:",
    ),
    # --- what may not be computed (api-015) ---------------------------------
    "a group's span starts where its first item does": (
        EVIDENCE,
        "                observedFrom=min(m.started_at for m in members).isoformat(),",
        "                observedFrom=members[0].started_at.isoformat(),",
    ),
    "a group counts one whatever it holds": (
        EVIDENCE,
        "                count=len(members),",
        "                count=1,",
    ),
    "identical absences are served one per episode": (
        EVIDENCE,
        "        if key not in counts:",
        "        if True:",
    ),
    # --- the pass stores what it builds (evb-003) ---------------------------
    "the pass goes back to throwing its accounts away": (
        CHAIN,
        "    save_bundles(session_factory, scenario_run_id=run.id, bundles=bundles)",
        "    _ = (session_factory, bundles)",
    ),
    "the pass swallows the refusal and stamps the run": (
        CHAIN,
        "    save_bundles(session_factory, scenario_run_id=run.id, bundles=bundles)",
        "    try:\n"
        "        save_bundles(session_factory, scenario_run_id=run.id, bundles=bundles)\n"
        "    except Exception:\n"
        "        pass",
    ),
    # --- the four states (op-010) -------------------------------------------
    "a failed fetch is reported as an unexamined hour": (
        PANEL,
        "        The evidence for this hour could not be loaded. This says nothing about the hour — only\n"
        "        that the request for it did not arrive.",
        "        This hour has not been examined, so there is nothing to explain yet.",
    ),
    "a quiet hour says nothing at all": (
        PANEL,
        "        Nothing was reported for this hour, so there is nothing to explain. The detectors looked\n"
        "        and found no conclusion to draw.",
        "        ",
    ),
    "a conclusion with no evidence renders an empty block": (
        PANEL,
        "        {account.unexplained.map((claim) => (",
        "        {[].map((claim: UnexplainedClaim) => (",
    ),
    "a judgement renders like a measurement": (
        PANEL,
        "        {groundingLabel(group.grounding)}",
        '        {""}',
    ),
    "the three kinds of not-knowing become one": (
        PANEL,
        "              {absenceLabel(absence.kind)}",
        '              {"Not known"}',
    ),
    "an absence statement is cut short": (
        PANEL,
        '            <dd className="text-sm text-[#c2c6d6]">{absence.statement}</dd>',
        '            <dd className="text-sm text-[#c2c6d6]">{absence.statement.slice(0, 40)}</dd>',
    ),
    "the collapsed count is dropped": (
        PANEL,
        "              {absence.count > 1 ? ` ×${absence.count}` : \"\"}",
        '              {""}',
    ),
    "a rejected conclusion is not shown as rejected": (
        PANEL,
        "    {claim.superseded.length > 0 && (",
        "    {false && (",
    ),
    "an evidence type reaches the screen as its raw token": (
        PANEL,
        '      <span className="text-sm">{verdict ? VERDICT : evidenceLabel(group.findingType)}</span>',
        '      <span className="text-sm">{group.findingType}</span>',
    ),
    # --- the fetch (op-010) --------------------------------------------------
    "a failed fetch is not reported as one": (
        HOOK,
        '        if (!cancelled) setView("failed");',
        '        if (!cancelled && false) setView("failed");',
    ),
    "the previous hour's evidence stays up while the next is in flight": (
        HOOK,
        '    setView("loading");',
        "    // back to loading on the way in",
    ),
    "a request in flight is reported as a failure": (
        PANEL,
        '      <p className="mt-4 text-sm text-[#8c909f]">Reading the evidence for this hour…</p>',
        "      <p className=\"mt-4 text-sm text-[#8c909f]\">could not be loaded</p>",
    ),
    "the fetcher renders whatever it is given": (
        API,
        "  if (payload !== null && !isAccount(payload)) {",
        "  if (false) {",
    ),
    # --- the contract (guarded by the backend suite) ------------------------
    "the contract loses a finding type the builder emits": (
        CONTRACT,
        '  | "channel_adjacency"\n',
        "",
    ),
    "a reason becomes a bare string": (
        CONTRACT,
        'export type UnexplainedReason = "not-bundled";',
        "export type UnexplainedReason = string;",
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
        EVIDENCE,
        "        runId=run_id,",
        "        runId=run_id + 1,",
        _backend_suite,
    ),
    (
        "frontend",
        PANEL,
        'aria-label="Evidence"',
        'aria-label="Nothing"',
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

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
unclear = [n for n, v in res.items() if v.startswith("INCONCLUSIVE")]
valid = len(res) - len(invalid) - len(unclear)
print(f"\n{killed} of {valid} valid mutants killed ({len(res)} attempted)")
for label, names in (
    ("SURVIVED", survived),
    ("INVALID", invalid),
    ("INCONCLUSIVE", unclear),
):
    for name in names:
        print(f"  {label}: {name}")
