"""Mutation pass over ai-008, the grounding check.

This is the safeguard every claim about the AI layer rests on, so the
question "would the tests notice if it stopped working" matters more here
than anywhere else in the package. A broken grounding check does not fail
loudly -- it returns "fine", every hypothesis reaches an analyst, and the
reported catch rate goes to zero while reading like a good result.

Four surfaces, failing in different ways.

**The resolution.** The mutants that matter most are the ones that still
resolve *something*: the rule id alone, or case-insensitively, or with the
superseded compartment folded into the citable set. Each produces a check
that passes the oracle perfectly -- a template hypothesis is grounded under
all of them -- and silently certifies the errors it exists to catch. The
corpus measurement beside this one cannot see them either, which is why
they are here.

**The compartment.** Making `SUPERSEDED` fold into `UNKNOWN`, or letting a
rejected claim win over an evidence item, or dropping the word "rejected"
from the sentence a human reads. The distinction exists in three places and
each has its own mutant, because a distinction that survives in the enum
and dies in the message is a distinction nobody acts on.

**The near misses.** These change no verdict, so nothing downstream
breaks and only a test looking directly at them notices. That is precisely
why they are the part of a reported figure most likely to rot.

**The ledger.** A rate of zero where nothing was measured; arms pooled; a
passing report counted as a catch. All three produce a number, which is
worse than producing none.

Run in the repository's own virtualenv rather than through Docker -- see
the note on `PYTEST` in `mutate_ai004_hosted.py` for why, why that is valid
for a file with no `database` marker, and the sentinel that makes it safe.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the repository root
BACKEND = ROOT / "backend"
SRC = BACKEND / "app/ai/grounding.py"
TESTS = "tests/test_ai_grounding.py"

#: See `mutate_ai004_hosted.py` for the full argument. In short: three
#: Docker passes were killed by the OOM killer, this file has no database
#: marker and gives an identical result either way, and the sentinel below
#: aborts the run if source edits stop reaching the tests.
PYTEST = [
    str(BACKEND / ".venv/bin/python"),
    "-m",
    "pytest",
    "-q",
    "--no-cov",
    "-p",
    "no:cacheprovider",
]

M = {
    # --- the resolution ----------------------------------------------------
    "the pair is resolved on the rule id alone": (
        SRC,
        "        if citation.finding_type in citable.get(citation.rule_id, ()):",
        "        if citation.rule_id in citable:"),
    "the pair is resolved on the finding type alone": (
        SRC,
        "        if citation.finding_type in citable.get(citation.rule_id, ()):",
        "        if any(citation.finding_type in t for t in citable.values()):"),
    "every citation is grounded": (
        SRC,
        "        if citation.finding_type in citable.get(citation.rule_id, ()):",
        "        if True:"),
    "no citation is ever grounded": (
        SRC,
        "        if citation.finding_type in citable.get(citation.rule_id, ()):",
        "        if False:"),
    "matching is case-insensitive": (
        SRC,
        "        if citation.finding_type in citable.get(citation.rule_id, ()):",
        "        if _spelling_near_miss(citation.rule_id, citation.finding_type, "
        "citable):"),
    "the bundle's own claim is citable as evidence for itself": (
        SRC,
        "        if citation.finding_type in citable.get(citation.rule_id, ()):",
        "        if citation.rule_id == bundle.rule_id or citation.finding_type in "
        "citable.get(citation.rule_id, ()):"),
    "the normalisation folds nothing": (
        SRC,
        '    return "".join(text.split()).casefold()',
        "    return text"),
    "the normalisation ignores case but not spacing": (
        SRC,
        '    return "".join(text.split()).casefold()',
        "    return text.casefold()"),
    "findings come back in reverse order": (
        SRC,
        "    return GroundingReport(findings=tuple(findings))",
        "    return GroundingReport(findings=tuple(reversed(findings)))"),
    "positions are zero-based": (
        SRC,
        "    for position, citation in enumerate(hypothesis.supporting_evidence, "
        "start=1):",
        "    for position, citation in enumerate(hypothesis.supporting_evidence, "
        "start=0):"),

    # --- the compartment ----------------------------------------------------
    "the superseded compartment is citable too": (
        SRC,
        "        if item.finding_type not in types:\n"
        "            types.append(item.finding_type)\n"
        "    return index",
        "        if item.finding_type not in types:\n"
        "            types.append(item.finding_type)\n"
        "    for claim in bundle.superseded:\n"
        "        index.setdefault(claim.rule_id, []).append(claim.anomaly_type)\n"
        "    return index"),
    "the rejected claims are never looked up": (
        SRC,
        "    rejected = _rejected_index(bundle)",
        "    rejected = {}"),
    "a rejected claim is reported as merely unknown": (
        SRC,
        "    if finding_type in rejected.get(rule_id, ()):",
        "    if False:"),
    "a rejected claim beats an evidence item carrying the same pair": (
        SRC,
        "        if citation.finding_type in citable.get(citation.rule_id, ()):",
        "        if citation.finding_type in citable.get(citation.rule_id, ()) and "
        "not rejected.get(citation.rule_id):"),
    "the superseded index reads the wrong field": (
        SRC,
        "        if claim.anomaly_type not in types:\n"
        "            types.append(claim.anomaly_type)",
        "        if claim.claimed_by not in types:\n"
        "            types.append(claim.claimed_by)"),
    "the sentence a human reads does not say the claim was rejected": (
        SRC,
        '                "cites a claim the rule ladder rejected in favour of this '
        'one. A "',
        '                "cites something outside the evidence list. A "'),
    "a misspelled rejected claim reads as an ordinary invention": (
        SRC,
        '                "is a claim the ladder rejected and could not be cited in '
        'support "',
        '                "is simply not in the evidence list "'),

    # --- the near misses ----------------------------------------------------
    "the spelling near miss is never looked for": (
        SRC,
        "    spelled = _spelling_near_miss(rule_id, finding_type, citable)",
        "    spelled = None"),
    "the rule-id near miss is never looked for": (
        SRC,
        "    if rule_id in citable:",
        "    if False:"),
    "the rule-id reading is preferred over the spelling one": (
        SRC,
        "    if spelled is not None:",
        "    if spelled is not None and rule_id not in citable:"),
    "a near miss softens the verdict to grounded": (
        SRC,
        "            verdict=CitationVerdict.UNKNOWN,\n"
        "            near_miss=NearMiss.CASE_OR_SPACING,\n"
        "            detail=(\n"
        '                f"names nothing the bundle carries; it differs from the '
        'evidence "',
        "            verdict=CitationVerdict.GROUNDED,\n"
        "            near_miss=NearMiss.CASE_OR_SPACING,\n"
        "            detail=(\n"
        '                f"names nothing the bundle carries; it differs from the '
        'evidence "'),
    "the near-miss detail does not name the types that are present": (
        SRC,
        "                f\"carries it as {', '.join(citable[rule_id])}\"",
        '                "carries it as something else"'),
    "every refusal is recorded as a near miss": (
        SRC,
        "        verdict=CitationVerdict.UNKNOWN,\n"
        '        detail="names nothing this bundle carries",',
        "        verdict=CitationVerdict.UNKNOWN,\n"
        "        near_miss=NearMiss.CASE_OR_SPACING,\n"
        '        detail="names nothing this bundle carries",'),
    "a grounded citation carries a detail too": (
        SRC,
        "                    verdict=CitationVerdict.GROUNDED,\n"
        "                )",
        "                    verdict=CitationVerdict.GROUNDED,\n"
        '                    detail="resolved",\n'
        "                )"),
    "the near-miss list holds every citation": (
        SRC,
        "        return tuple(f for f in self.findings if f.near_miss is not None)",
        "        return tuple(self.findings)"),

    # --- the report ---------------------------------------------------------
    "one ungrounded citation no longer fails the report": (
        SRC,
        "        return all(finding.grounded for finding in self.findings)",
        "        return any(finding.grounded for finding in self.findings)"),
    "every report passes": (
        SRC,
        "        return all(finding.grounded for finding in self.findings)",
        "        return True"),
    "the ungrounded list holds every citation": (
        SRC,
        "        return tuple(f for f in self.findings if not f.grounded)",
        "        return tuple(self.findings)"),
    "a failing report says nothing": (
        SRC,
        "        failures = self.ungrounded\n"
        "        if not failures:",
        "        failures = ()\n"
        "        if not failures:"),
    "a passing report carries a reason too": (
        SRC,
        "        if not failures:\n"
        '            return ""',
        "        if False:\n"
        '            return ""'),
    "the reason does not say which citation failed": (
        SRC,
        '                f"citation {f.position} ({f.rule_id}/{f.finding_type}) '
        '{f.detail}"',
        '                f"({f.rule_id}/{f.finding_type}) {f.detail}"'),
    "the reason does not name the failing identifiers": (
        SRC,
        '                f"citation {f.position} ({f.rule_id}/{f.finding_type}) '
        '{f.detail}"',
        '                f"citation {f.position} {f.detail}"'),

    # --- the surface ai-007 injects -----------------------------------------
    "the gate never raises": (
        SRC,
        "        if not outcome.passed:\n"
        "            raise GenerationRefused(outcome.reason)",
        "        if False:\n"
        "            raise GenerationRefused(outcome.reason)"),
    "the gate raises on a hypothesis that passed": (
        SRC,
        "        if not outcome.passed:\n"
        "            raise GenerationRefused(outcome.reason)",
        "        if outcome.passed:\n"
        "            raise GenerationRefused(outcome.reason)"),
    "the refusal carries no reason": (
        SRC,
        "            raise GenerationRefused(outcome.reason)",
        '            raise GenerationRefused("ungrounded")'),
    "the gate raises something ai-007 does not catch": (
        SRC,
        "            raise GenerationRefused(outcome.reason)",
        "            raise ValueError(outcome.reason)"),
    "the check launders its own defects into a refusal": (
        SRC,
        "        outcome = self.report(hypothesis, bundle)\n"
        "        if not outcome.passed:",
        "        try:\n"
        "            outcome = self.report(hypothesis, bundle)\n"
        "        except Exception as error:\n"
        "            raise GenerationRefused(str(error)) from error\n"
        "        if not outcome.passed:"),
    "the gate does not record into the ledger": (
        SRC,
        "        outcome = self.report(hypothesis, bundle)\n"
        "        if not outcome.passed:",
        "        outcome = check(hypothesis, bundle)\n"
        "        if not outcome.passed:"),
    "the reporting surface does not record either": (
        SRC,
        "        if self.ledger is not None:\n"
        "            self.ledger.record(self.arm, outcome)",
        "        if False:\n"
        "            self.ledger.record(self.arm, outcome)"),

    # --- the ledger ---------------------------------------------------------
    "an arm that was never checked reports a rate of zero": (
        SRC,
        "        if total == 0:\n"
        "            return None",
        "        if total == 0:\n"
        "            return 0.0"),
    "the catch rate is inverted": (
        SRC,
        "        return self.caught(arm) / total",
        "        return 1 - self.caught(arm) / total"),
    "a hypothesis that passed is counted as a catch": (
        SRC,
        "        return sum(1 for record in self._for(arm) if not "
        "record.report.passed)",
        "        return sum(1 for record in self._for(arm) if record.report.passed)"),
    "the arms are pooled": (
        SRC,
        "        return [record for record in self._records if record.arm is arm]",
        "        return list(self._records)"),
    "ordinals restart at one for every record": (
        SRC,
        "        entry = GroundingRecord(ordinal=len(self._records) + 1, arm=arm, "
        "report=report)",
        "        entry = GroundingRecord(ordinal=1, arm=arm, report=report)"),
    "the ledger hands out its live list": (
        SRC,
        "        return tuple(self._records)",
        "        return self._records"),
    "near misses come back pooled across arms": (
        SRC,
        "            for record in self._for(arm)\n"
        "            for finding in record.report.near_misses",
        "            for record in self._records\n"
        "            for finding in record.report.near_misses"),
}

#: Survivors argued to be equivalent go here, with the argument. Empty
#: until the first pass says otherwise -- a name added before the pass runs
#: is a prediction, not a finding.
EXPECTED_EQUIVALENT: set[str] = set()

originals = {SRC: SRC.read_text()}

# --- the crash guard ------------------------------------------------------
# A `finally` does not survive a SIGKILL, and the OOM killer has stranded a
# mutant in this working tree twice. The guard file holds the originals, so
# a run that dies puts them back on the next start rather than leaving a
# mutated module looking like ordinary uncommitted work.
GUARD = Path(__file__).with_suffix(".in-progress.json")

if GUARD.exists():
    for name, text in json.loads(GUARD.read_text()).items():
        Path(name).write_text(text)
    GUARD.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. "
        "The originals have been put back from the guard file. Check "
        "`git diff` is clean, then run again."
    )

GUARD.write_text(json.dumps({str(k): v for k, v in originals.items()}))


def run_suite() -> tuple[int, str, bool]:
    proc = subprocess.run(
        [*PYTEST, TESTS], cwd=BACKEND, capture_output=True, text=True
    )
    lines = [
        line.strip()
        for line in proc.stdout.splitlines()
        if "passed" in line or "failed" in line or "error" in line
    ]
    summary = lines[-1] if lines else "NO TEST SUMMARY -- did the suite run?"
    return proc.returncode, summary, ("passed" in summary or "failed" in summary)


# --- the sentinel ---------------------------------------------------------
# One deliberately broken edit before anything is scored. A harness
# reporting a perfect score without running a test is the defect this
# directory has recorded twice, so the assumption that an edit reaches the
# tests is checked rather than held.
_sentinel_from = "        return all(finding.grounded for finding in self.findings)"
_sentinel_original = originals[SRC]
SRC.write_text(
    _sentinel_original.replace(_sentinel_from, "        return False", 1)
)
_code, _summary, _ran = run_suite()
SRC.write_text(_sentinel_original)
if not _ran:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(f"the suite did not run at all: {_summary}")
if not _code:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(
        "SENTINEL SURVIVED. A deliberately broken source edit left the suite "
        f"green ({_summary}), so edits are not reaching the tests and no score "
        "from this harness can be believed."
    )
print(f"sentinel killed ({_summary}) -- source edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        orig = originals[path]
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        path.write_text(orig.replace(o, w, 1))
        code, summary, ran = run_suite()
        if not ran:
            res[n] = f"INCONCLUSIVE -- {summary}"
        else:
            res[n] = ("KILLED   " if code else "SURVIVED ") + summary
        print(f"{n:62} {res[n]}", flush=True)
        path.write_text(orig)
finally:
    for path, text in originals.items():
        path.write_text(text)
    GUARD.unlink(missing_ok=True)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
unclear = [n for n, v in res.items() if v.startswith("INCONCLUSIVE")]
print(f"\n{killed} killed of {len(res) - len(invalid) - len(unclear)} valid mutants")
if invalid:
    print(f"INVALID (the anchor did not match exactly once): {invalid}")
if unclear:
    print(f"INCONCLUSIVE (no test summary -- the suite may not have run): {unclear}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
