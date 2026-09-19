"""Mutation pass over ai-001, the hypothesis output schema.

A schema is where a mutation pass is unusually informative, because almost
every defect in one is a **silent widening**. A schema that accepts more
than it should does not fail; it passes everything it used to and admits
something new, and the thing it admits arrives at whatever is downstream
looking well-formed. That is the opposite of a crash and much harder to
notice.

So nearly every site below widens rather than breaks: a required field
given a default, a floor removed, an enum gaining a value, whitespace
stopped being stripped, unknown fields permitted. A suite that does not
kill these is a suite asserting that valid input validates.

The derived-schema sites are the other half and the half more easily
forgotten. `hypothesis_json_schema()` is what actually constrains a hosted
generation, so a mutation that returns a shared dictionary, or that loses
the enum, breaks a guarantee no local test would otherwise exercise --
every Python-side test would still pass while the model generating against
the derived schema was free.
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/ai/hypothesis.py"
T = "tests/test_ai_schema.py"
PY_BIN = os.environ.get("PY_BIN", str(ROOT / ".venv/bin/python"))

M = {
  # --- confidence is three words and never a number ----------------------
  "confidence becomes a free string": (
      "    confidence: Confidence\n", "    confidence: str\n"),
  "a fourth confidence level is added": (
      '    HIGH = "High"', '    HIGH = "High"\n    VERY_HIGH = "Very High"'),
  "confidence is spelled lower case": (
      '    LOW = "Low"\n    MEDIUM = "Medium"\n    HIGH = "High"',
      '    LOW = "low"\n    MEDIUM = "medium"\n    HIGH = "high"'),

  # --- nothing defaults ---------------------------------------------------
  "the alternatives default to empty": (
      "    alternative_explanations: Annotated[tuple[str, ...], Field(min_length=1)]",
      "    alternative_explanations: tuple[str, ...] = ()"),
  "the uncertainty list defaults to empty": (
      "    evidence_against_or_uncertainty: tuple[str, ...]",
      "    evidence_against_or_uncertainty: tuple[str, ...] = ()"),
  "the recommended action defaults to nothing": (
      "    recommended_human_action: NonBlank",
      '    recommended_human_action: NonBlank = "none"'),
  "the summary defaults to nothing": (
      "    summary: NonBlank", '    summary: NonBlank = "none"'),

  # --- the floors ---------------------------------------------------------
  "a hypothesis may cite nothing": (
      "    supporting_evidence: Annotated[tuple[Citation, ...], Field(min_length=1)]",
      "    supporting_evidence: tuple[Citation, ...]"),
  "a hypothesis may name no alternatives": (
      "    alternative_explanations: Annotated[tuple[str, ...], Field(min_length=1)]",
      "    alternative_explanations: tuple[str, ...]"),
  "the uncertainty list acquires a floor it must not have": (
      "    evidence_against_or_uncertainty: tuple[str, ...]",
      "    evidence_against_or_uncertainty: Annotated[tuple[str, ...], "
      "Field(min_length=1)]"),

  # --- a citation is structured, and the pair identifies it ---------------
  "supporting evidence becomes prose": (
      "    supporting_evidence: Annotated[tuple[Citation, ...], Field(min_length=1)]",
      "    supporting_evidence: Annotated[tuple[str, ...], Field(min_length=1)]"),
  "a citation drops the finding type": (
      "    rule_id: NonBlank\n    finding_type: NonBlank\n    statement: NonBlank",
      "    rule_id: NonBlank\n    statement: NonBlank"),
  "a citation's finding type becomes optional": (
      "    finding_type: NonBlank\n", '    finding_type: NonBlank = "unknown"\n'),

  # --- text that is not text ----------------------------------------------
  "whitespace is no longer stripped before the length check": (
      "StringConstraints(strip_whitespace=True, min_length=1)",
      "StringConstraints(strip_whitespace=False, min_length=1)"),
  "an empty string counts as text": (
      "StringConstraints(strip_whitespace=True, min_length=1)",
      "StringConstraints(strip_whitespace=True, min_length=0)"),

  # --- the model's own guarantees -----------------------------------------
  "unknown fields are carried rather than refused": (
      'model_config = ConfigDict(frozen=True, extra="forbid")',
      'model_config = ConfigDict(frozen=True, extra="allow")'),
  "a hypothesis can be edited after validation": (
      'model_config = ConfigDict(frozen=True, extra="forbid")',
      'model_config = ConfigDict(frozen=False, extra="forbid")'),

  # --- the derived schema, which is what constrains a hosted generation ---
  "the derived schema is shared rather than copied": (
      "    return copy.deepcopy(Hypothesis.model_json_schema())",
      "    return Hypothesis.model_json_schema()"),
}

#: Established by the first pass rather than predicted. Pydantic returns a
#: freshly constructed schema on every call, nested objects included --
#: checked directly -- so the deep copy is redundant at this pinned version
#: and no test can tell the two apart. It is kept as defence against that
#: changing quietly on an upgrade, where the failure would be a caller
#: adjusting one request's schema and silently changing what every later
#: generation is constrained by. Recorded here rather than removed, because
#: the precedent both ways exists in this directory: `anom-007` dropped a
#: site as a redundant guarantee, and this one guards a version boundary
#: rather than a second copy of a live check.
EXPECTED_EQUIVALENT = {"the derived schema is shared rather than copied"}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:56} {res[n]}", flush=True)
            continue
        F.write_text(orig.replace(o, w, 1))
        # Clear the bytecode cache every time: CPython validates a `.pyc` on
        # the source's (mtime-in-whole-seconds, size), and two consecutive
        # mutants changing the file by the same number of bytes would
        # otherwise run the first one's bytecode. It scored two
        # genuinely-killed `evb-001` mutants as SURVIVED.
        shutil.rmtree(F.parent / "__pycache__", ignore_errors=True)
        p = subprocess.run([PY_BIN, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        t = [l for l in p.stdout.splitlines()
             if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:56} {res[n]}", flush=True)
finally:
    F.write_text(orig)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
print(f"\n{killed} killed of {len(res) - len(invalid)} valid mutants")
if invalid:
    print(f"INVALID (the anchor did not match exactly once): {invalid}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
expected = [n for n in survived if n in EXPECTED_EQUIVALENT]
if expected:
    print("SURVIVED, and equivalent -- see the note above:")
    for n in expected:
        print(f"  - {n}")
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
