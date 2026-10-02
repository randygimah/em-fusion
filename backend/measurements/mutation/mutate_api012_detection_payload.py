"""Mutation pass over api-012 and anom-015's second amendment.

**Almost every mutant here leaves the endpoint serving a plausible payload.**
That is the shape of the risk and the reason this pass matters more than most:
the screen renders, the levels are bands rather than percentages, the receivers
appear, and the one thing that is wrong is a distinction nobody can see. The
defect this item exists to close was exactly that -- three fields read by three
planned panels, written by nothing, for a reason that had stopped being true,
and no test anywhere could have failed.

Five surfaces.

**Zero, which is the item.** A quiet run and a run nobody examined both produce
no detections, and `db-008` replaces findings per run per rule *including at
zero*, so the table cannot tell them apart. Every mutant that breaks the stamp
-- not written, written early, read back without checking it is set, written
without a predicate -- puts the endpoint back where it was, reporting an
unexamined run as a clean one. None of them raises anything.

**The conclusions being persisted at all.** `anom-015` wrote its evidence and
not its conclusions, which inside one process is invisible: the assessment it
returns is complete either way, and only another process can tell. Mutants that
drop a write, or write a claim the ladder suppressed, or match claims by
equality rather than identity, all leave `assess` returning exactly what it
returned before.

**The account.** `anom-008`'s argument is that completeness answers *did this
detector look* and a count never can, so an account missing its zeroes is the
failure mode, not a wrong number. A zero for a rule that does not exist is the
other direction, and `anom-008`'s own words for it: quoting the absence of a
rule as the accuracy of one.

**The two levels, and what each is about.** The worst deviation rather than the
first or the mildest; the receiver layout's state rather than the deviations
again; a level refused rather than laundered by `.title()`, which is `ai-002`'s
recorded trap.

**The answer key.** `scenario.name` served the run's scenario type until this
item, so the screen's heading read `gnss-degradation` -- `api-009`'s named
failure case, live. The mutant puts it back, and it is the one mutant whose
survival would mean a guarantee is unasserted rather than a figure is wrong.

Four files, because the item is a seam: the pass writes, the repository stamps
and reads, the converter shapes, the payload assembles.

Runs in the container, because half of these are only observable against a
database -- a host-only run would skip every chain and repository test and score
their mutants as survivors of a suite that never ran them.

Run: `python measurements/mutation/mutate_api012_detection_payload.py` from
`backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PAYLOAD = BACKEND / "app/api/v1/schemas/operational_picture.py"
CHAIN = BACKEND / "app/detection/chain.py"
REPOSITORY = BACKEND / "app/db/repository.py"
CONVERTERS = BACKEND / "app/detection/findings.py"
FILES = (PAYLOAD, CHAIN, REPOSITORY, CONVERTERS)
TESTS = [
    "tests/test_api_operational_picture.py",
    "tests/test_anom_chain.py",
    "tests/test_db_repository.py",
    "tests/test_api_route_purity.py",
]

#: name -> (file, anchor, replacement)
M: dict[str, tuple[Path, str, str]] = {
    # --- zero: unexamined against clean --------------------------------------
    "an unexamined run is served a detection summary anyway": (
        PAYLOAD,
        "    scored = detection_pass is not None",
        "    scored = True",
    ),
    "the pass leaves no record that it ran": (
        CHAIN,
        "    record_detection_pass(\n"
        "        session_factory,  # type: ignore[arg-type]\n"
        "        run.id,\n"
        "        policy=policy,\n"
        "    )",
        "    pass",
    ),
    "the run is stamped before its findings are written": (
        CHAIN,
        "    policy = policies.record(normality, layout=layout)",
        "    policy = policies.record(normality, layout=layout)\n"
        "    record_detection_pass(\n"
        "        session_factory,  # type: ignore[arg-type]\n"
        "        run.id,\n"
        "        policy=policy,\n"
        "    )",
    ),
    "a run with an unset stamp reads as examined": (
        REPOSITORY,
        '    if row is None or row["detection_pass_at"] is None:',
        "    if row is None:",
    ),
    "stamping one run stamps every run": (
        REPOSITORY,
        '                "    detection_policy = CAST(:policy AS jsonb) "\n'
        '                "WHERE id = :run_id"',
        '                "    detection_policy = CAST(:policy AS jsonb) "',
    ),
    "a stamp that matched no run is reported as written": (
        REPOSITORY,
        "        if result.rowcount != 1:\n"
        "            raise LookupError(\n"
        '                f"scenario run {run_id} does not exist, so a detection pass "',
        "        if False:\n"
        "            raise LookupError(\n"
        '                f"scenario run {run_id} does not exist, so a detection pass "',
    ),
    "the stamp carries no policy": (
        REPOSITORY,
        '    return DetectionPass(\n'
        '        scenario_run_id=row["id"],\n'
        '        at=row["detection_pass_at"],\n'
        '        policy=dict(row["detection_policy"] or {}),\n'
        "    )",
        '    return DetectionPass(\n'
        '        scenario_run_id=row["id"],\n'
        '        at=row["detection_pass_at"],\n'
        "        policy={},\n"
        "    )",
    ),
    # --- the conclusions, persisted ------------------------------------------
    "the fault attributions are not written down": (
        CHAIN,
        "        rule_id=FAULT_RULE,\n"
        "        findings=[f for f in conclusions if f.rule_id == FAULT_RULE],",
        "        rule_id=FAULT_RULE,\n        findings=[],",
    ),
    "the interference zones are not written down": (
        CHAIN,
        "        rule_id=FUSION_RULE,\n"
        "        findings=[f for f in conclusions if f.rule_id == FUSION_RULE],",
        "        rule_id=FUSION_RULE,\n        findings=[],",
    ),
    "a claim the ladder suppressed is written beside the one that beat it": (
        CHAIN,
        "        finding for claim, finding in evidence "
        "if any(claim is won for won in reported)",
        "        finding for claim, finding in evidence",
    ),
    "claims are matched to their findings by value rather than identity": (
        CHAIN,
        "if any(claim is won for won in reported)",
        "if any(claim == won for won in reported)",
    ),
    "a zone's row keeps only the receiver it is filed under": (
        CONVERTERS,
        '            "sensors": list(zone.sensors),',
        '            "sensors": [zone.sensors[0]],',
    ),
    "a fault's row loses the neighbours its attribution rested on": (
        CONVERTERS,
        '            "neighbours": list(fault.spatial.neighbours),',
        '            "neighbours": [],',
    ),
    # --- the account ---------------------------------------------------------
    "the account lists only the producers that found something": (
        PAYLOAD,
        "        entries.append(",
        "        if not _of(findings, key):\n            continue\n        entries.append(",
    ),
    "a rule that does not exist reports zero": (
        PAYLOAD,
        "            RULE_NOT_BUILT\n            if not producer.built",
        "            None\n            if not producer.built",
    ),
    "a producer whose findings are not stored reports zero": (
        PAYLOAD,
        "            else NOT_PERSISTED if key not in PERSISTED_PRODUCERS else None",
        "            else None",
    ),
    "every producer is labelled a conclusion": (
        PAYLOAD,
        "                kind=producer.kind.value,",
        '                kind="reportable",',
    ),
    "the account keys on the rule and not on the pair": (
        PAYLOAD,
        "def _of(findings: Sequence[DetectionFinding], key: Key) "
        "-> list[DetectionFinding]:\n"
        "    return [f for f in findings if (f.rule_id, f.finding_type) == key]",
        "def _of(findings: Sequence[DetectionFinding], key: Key) "
        "-> list[DetectionFinding]:\n"
        "    return [f for f in findings if f.rule_id == key[0]]",
    ),
    "a count may sit beside a reason for its own absence": (
        PAYLOAD,
        "        if (self.count is None) == (self.unavailable is None):",
        "        if False:",
    ),
    "the persisted set omits a rule the pass does write": (
        PAYLOAD,
        "        (FAULT_RULE, FAULT_TYPE),\n        (FUSION_RULE, INTERFERENCE_TYPE),",
        "        (FUSION_RULE, INTERFERENCE_TYPE),",
    ),
    # --- the two levels ------------------------------------------------------
    "the anomaly level is the mildest deviation rather than the worst": (
        PAYLOAD,
        '        "High"\n'
        '        if "High" in severities\n'
        '        else "Medium" if "Medium" in severities else "Low"',
        '        "Low"\n'
        '        if "Low" in severities\n'
        '        else "Medium" if "Medium" in severities else "High"',
    ),
    "a stored level is capitalised rather than refused": (
        PAYLOAD,
        "    if isinstance(word, str) and word.upper() in _LEVELS:\n"
        "        return _LEVELS[word.upper()]",
        "    if isinstance(word, str):\n"
        "        return word.title()  # type: ignore[return-value]",
    ),
    "signal integrity reads the deviations rather than the receivers": (
        PAYLOAD,
        '        "Low" if FAULT in states else "Medium" if DEVIATING in states else "High"',
        '        "Low" if "high" in severities '
        'else "Medium" if "medium" in severities else "High"',
    ),
    "a broken receiver leaves signal integrity no worse than a loud one": (
        PAYLOAD,
        '        "Low" if FAULT in states else "Medium" if DEVIATING in states else "High"',
        '        "Medium" if FAULT in states or DEVIATING in states else "High"',
    ),
    # --- the receivers -------------------------------------------------------
    "a receiver nothing has examined reports itself nominal": (
        PAYLOAD,
        "        return {site.sensor_id: UNKNOWN for site in layout.sensors}",
        "        return {site.sensor_id: NOMINAL for site in layout.sensors}",
    ),
    "the receiver strip is served only for a run that was examined": (
        PAYLOAD,
        "        rfSensors=[\n            RFSensor(",
        "        rfSensors=[] if not scored else [\n            RFSensor(",
    ),
    "a deviating reading overwrites a fault attribution": (
        PAYLOAD,
        "    for key, value in reversed(RECEIVER_STATES):",
        "    for key, value in RECEIVER_STATES:",
    ),
    "an interference zone marks its receivers broken": (
        PAYLOAD,
        "    ((FUSION_RULE, INTERFERENCE_TYPE), DEVIATING),",
        "    ((FUSION_RULE, INTERFERENCE_TYPE), FAULT),",
    ),
    "a finding naming a receiver outside the layout is dropped": (
        PAYLOAD,
        "                if sensor not in state:\n                    raise PictureError(",
        "                if False:\n                    raise PictureError(",
    ),
    # --- the timeline --------------------------------------------------------
    "the timeline lists the working material beside the conclusions": (
        PAYLOAD,
        "    claims = [f for f in findings if (f.rule_id, f.finding_type) in reportable]",
        "    claims = list(findings)",
    ),
    "the timeline arrives in whatever order the store returned": (
        PAYLOAD,
        "    claims.sort(key=lambda f: (f.started_at, f.subject, f.finding_type))",
        "    pass",
    ),
    "a timeline event is a sentence rather than the finding type": (
        PAYLOAD,
        "            event=f.finding_type,",
        '            event=f"Anomaly detected on {f.subject}",',
    ),
    # --- the answer key ------------------------------------------------------
    "the screen's heading announces the scenario type again": (
        PAYLOAD,
        "            name=f\"Run {run.id}\",",
        "            name=run.scenario_type,",
    ),
}

EXPECTED_EQUIVALENT: dict[str, str] = {}

RAN = re.compile(r"(\d+) (?:passed|failed)")
ORIGINALS = {path: path.read_text() for path in FILES}

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


def _suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        ["make", "test-backend-nobuild", f"PYTEST_ARGS={' '.join(TESTS)} -q --no-cov"],
        cwd=str(BACKEND.parent),
        capture_output=True,
        text=True,
    )
    tail = [
        line
        for line in p.stdout.splitlines()
        if "passed" in line or "failed" in line or "error" in line
    ]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(RAN.search(summary))


# --- the sentinel ---------------------------------------------------------
# A deliberately broken edit. If the suite stays green, edits are not reaching
# the tests and no score from this harness means anything.
_from = "    scored = detection_pass is not None"
assert ORIGINALS[PAYLOAD].count(_from) == 1
PAYLOAD.write_text(ORIGINALS[PAYLOAD].replace(_from, "    scored = False", 1))
_code, _summary, _ran = _suite()
_restore()
if not _ran:
    GUARD_FILE.unlink(missing_ok=True)
    raise SystemExit(f"the suite did not run at all: {_summary}")
if not _code:
    GUARD_FILE.unlink(missing_ok=True)
    raise SystemExit(
        "SENTINEL SURVIVED. A deliberately broken source edit left the suite "
        f"green ({_summary}), so edits are not reaching the tests."
    )
print(f"sentinel killed ({_summary}) -- source edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        original = ORIGINALS[path]
        if original.count(o) != 1:
            res[n] = f"INVALID ({original.count(o)})"
            print(f"{n:70} {res[n]}", flush=True)
            continue
        mutated = original.replace(o, w, 1)
        # A mutant that does not parse tests nothing: it is killed by a syntax
        # error rather than by a test, which scores a gap as a pass.
        try:
            ast.parse(mutated)
        except SyntaxError as broken:
            res[n] = f"INVALID (does not parse: {broken.msg})"
            print(f"{n:70} {res[n]}", flush=True)
            continue
        # A mutant identical to the original tests nothing either, and reads as
        # a survivor -- the sixth hazard in measurements/README.md, and one
        # anom-011's pass actually hit.
        if mutated == original:
            res[n] = "INVALID (identical to the original)"
            print(f"{n:70} {res[n]}", flush=True)
            continue
        path.write_text(mutated)
        code, summary, ran = _suite()
        res[n] = (
            f"INCONCLUSIVE -- {summary}"
            if not ran
            else ("KILLED   " if code else "SURVIVED ") + summary
        )
        print(f"{n:70} {res[n]}", flush=True)
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
